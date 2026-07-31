"""Que las alertas existan, sean únicas y no apunten a métricas que nadie publica.

Una alerta sobre una métrica mal escrita es sintácticamente perfecta y **nunca dispara**: no
falla, no loguea, no aparece en ninguna pestaña. Es indistinguible de un sistema sano, así que
cae en la misma familia que el resto de fallas silenciosas del proyecto y necesita un test que
la haga ruidosa.

Estos tests son estáticos, sin docker: fijan el cableado (una sola fuente de reglas, la ruta que
Prometheus va a buscar, los nombres de métrica contra el código). Que las reglas **disparen** en
el escenario correcto lo prueba `observability/alerts_test.yml` con `promtool test rules`, que
corre en CI — acá se fija además que ninguna alerta se agregue sin su caso de prueba.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Las reglas viven dentro del chart porque Helm solo lee archivos de adentro del chart; el
# compose las hornea desde ahí. Ver observability/prometheus.Dockerfile.
ALERTAS = ROOT / "helm" / "teleflow" / "alerts" / "alerts.yml"
ALERTAS_TEST = ROOT / "observability" / "alerts_test.yml"
PROMETHEUS_YML = ROOT / "observability" / "prometheus.yml"
PROMETHEUS_DOCKERFILE = ROOT / "observability" / "prometheus.Dockerfile"
PLANTILLA_OBSERVABILIDAD = ROOT / "helm" / "teleflow" / "templates" / "observabilidad.yaml"


def texto(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def nombres_de_alerta() -> list[str]:
    return re.findall(r"^\s*- alert: (\w+)", texto(ALERTAS), re.MULTILINE)


def bloques_de_alerta() -> dict[str, str]:
    """Cada alerta con su cuerpo, cortando en la siguiente `- alert:` (o el fin del archivo)."""
    partes = re.split(r"^\s*- alert: ", texto(ALERTAS), flags=re.MULTILINE)[1:]
    return {parte.split("\n", 1)[0].strip(): parte for parte in partes}


def test_hay_alertas_definidas():
    assert nombres_de_alerta(), "no hay ninguna alerta declarada en alerts.yml"


def test_las_alertas_apuntan_a_metricas_que_el_codigo_publica():
    """El modo de falla que motiva este archivo: un nombre mal escrito no dispara nunca."""
    publicadas = set()
    for fuente in (ROOT / "teleflow").rglob("*.py"):
        publicadas |= set(re.findall(r'"(teleflow_[a-z0-9_]+)"', fuente.read_text("utf-8")))

    referidas = set(re.findall(r"\bteleflow_[a-z0-9_]+\b", texto(ALERTAS)))

    # Guarda contra un test vacuo: si el regex dejara de matchear, `referidas` quedaría vacío y
    # la comparación de abajo pasaría sin mirar nada. Esta métrica es la razón de ser del
    # archivo de alertas, así que tiene que estar sí o sí.
    assert "teleflow_business_metrics_last_success_timestamp_seconds" in referidas, (
        "no se pudo extraer ninguna métrica conocida de alerts.yml — el test no está mirando "
        "lo que cree"
    )
    assert publicadas, "no se pudo extraer ninguna métrica del código: el test no prueba nada"

    huerfanas = referidas - publicadas
    assert not huerfanas, (
        f"las alertas nombran métricas que ningún servicio publica: {sorted(huerfanas)}. "
        f"Una regla sobre una métrica inexistente no falla ni avisa: simplemente nunca dispara."
    )


def test_cada_alerta_dice_qué_pasa_y_cuán_grave_es():
    for nombre, cuerpo in bloques_de_alerta().items():
        assert "severity:" in cuerpo, f"{nombre} no declara severity: el ruteo no sabe a quién avisar"
        assert "summary:" in cuerpo, f"{nombre} no tiene summary: quien la reciba no sabe qué pasa"
        assert "description:" in cuerpo, f"{nombre} no tiene description: falta qué hacer con ella"
        assert re.search(r"^\s+for: ", cuerpo, re.MULTILINE), (
            f"{nombre} no declara `for`: dispara con un solo scrape fallido y se vuelve ruido, "
            f"que termina en que nadie mire las alertas."
        )


def test_cada_alerta_tiene_un_caso_de_prueba():
    """Sin esto, agregar una regla nueva y que nunca dispare pasa CI sin que nada lo note."""
    prueba = texto(ALERTAS_TEST)
    sin_probar = [n for n in nombres_de_alerta() if f"alertname: {n}" not in prueba]

    assert not sin_probar, (
        f"estas alertas no aparecen en observability/alerts_test.yml: {sin_probar}. "
        f"`promtool check rules` las valida sintácticamente pero no prueba que disparen."
    )


def test_prometheus_carga_el_archivo_de_reglas_que_la_imagen_copia():
    """Si `rule_files` y el `COPY` no coinciden, Prometheus no arranca (y eso está bien).

    Lo que este test evita es lo contrario: que alguien "arregle" el arranque sacando el
    `rule_files` en vez de arreglar la ruta, y el stack quede sin alertas y en verde.
    """
    destino = re.search(
        r"^COPY \S*alerts\.yml (\S+)", texto(PROMETHEUS_DOCKERFILE), re.MULTILINE
    )
    assert destino, "prometheus.Dockerfile no copia alerts.yml a la imagen"

    rule_files = re.search(r"^rule_files:\n((?:\s+- .+\n)+)", texto(PROMETHEUS_YML), re.MULTILINE)
    assert rule_files, "prometheus.yml no declara rule_files: las alertas no se cargarían"
    assert destino.group(1) in rule_files.group(1), (
        f"rule_files no incluye {destino.group(1)}, que es donde la imagen deja las reglas"
    )


def test_el_compose_y_el_chart_leen_el_mismo_archivo_de_reglas():
    """Dos copias de un archivo de alertas se desincronizan sin que nada avise.

    Es el mismo arreglo que ya tienen los dashboards: la fuente vive adentro del chart y el
    compose la copia desde ahí, en vez de que cada uno tenga la suya.
    """
    ruta_relativa_al_chart = ALERTAS.relative_to(ROOT / "helm" / "teleflow").as_posix()

    assert f'.Files.Get "{ruta_relativa_al_chart}"' in texto(PLANTILLA_OBSERVABILIDAD), (
        f"la plantilla del chart no lee {ruta_relativa_al_chart}: si tiene las reglas escritas "
        f"adentro, son una segunda copia que se va a desincronizar del compose."
    )
    assert ALERTAS.relative_to(ROOT).as_posix() in texto(PROMETHEUS_DOCKERFILE), (
        "la imagen de Prometheus del compose no copia las reglas del chart"
    )
    assert not (ROOT / "observability" / "alerts.yml").exists(), (
        "apareció una segunda copia de las reglas en observability/: la fuente única está en "
        f"{ALERTAS.relative_to(ROOT).as_posix()}"
    )
