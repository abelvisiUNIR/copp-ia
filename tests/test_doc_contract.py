"""Que lo que la documentación manda ejecutar exista de verdad.

Sale de un hecho medido, no de una preocupación: escribir el checklist de instalación
ejecutándolo encontró que el comando de producción de `docs/teleflow-deployment.typ` fallaba en
el **primer intento** —mandaba `-f values-production.yaml` y el archivo está en
`helm/teleflow/`— y que la lista de pendientes de `values-production.yaml` daba por pendientes
cosas hechas diez días antes. Ninguno de los dos se había visto en semanas de trabajo sobre esos
mismos archivos: **la documentación no tiene quien la ejecute, así que envejece sin avisar.**
Es la segunda vez que pasa (la primera fue el runbook del 2026-08-08, que citaba una tabla
inexistente).

Este test cubre la mitad **determinista** del problema, que es la que se puede gatear sin red y
sin cluster: que las rutas y las claves de `values` que la doc nombra existan. Es el mismo
reparto que `verificar_imagenes.py` — lo que se puede probar estático corta el merge; lo que
depende de un tercero va aparte.

**Lo que este test NO puede probar, y conviene no creer que sí:** que la prosa describa bien el
comportamiento. Que un comando exista no significa que haga lo que el párrafo de al lado dice.
Eso sigue necesitando ejecutar la doc de vez en cuando (`docs/checklist-instalacion.md`,
`docs/runbooks.md`).
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
VALUES = ROOT / "helm" / "teleflow" / "values.yaml"

# Se revisan los documentos operativos: los que alguien sigue con la terminal abierta. La doc de
# arquitectura (`TeleFlow-Arquitectura-v1.0.md`) queda afuera a propósito — es la consolidada,
# es más vieja que el código por diseño y el README ya declara sus discrepancias conocidas.
DOCS = (
    ROOT / "README.md",
    ROOT / "docs" / "checklist-instalacion.md",
    ROOT / "docs" / "runbooks.md",
    ROOT / "docs" / "teleflow-deployment.typ",
)

# Carpetas de primer nivel del repo. Un token que empieza con una de estas es una ruta del
# repo y tiene que existir; cualquier otra cosa (una ruta del cluster, un ejemplo, una URL) no
# se toca.
RAICES = ("helm/", "docs/", "tests/", "teleflow/", "scripts/", "examples/",
          "review-ui/", "observability/", "alembic/", ".github/")

# Marcadores de que el token es un ejemplo para completar, no una ruta real.
PLACEHOLDER = re.compile(r"[<>{}$*]|\.\.\.")

# Solo se comprueban tokens con extensión de archivo. Empezar con una carpeta del repo no
# alcanza para ser una ruta: `(teleflow/teleflow)` es el usuario/password de RabbitMQ en el
# README y `teleflow/teleflow:1.0.0` es una imagen. Los dos empiezan igual que una ruta y
# ninguno lo es. A cambio de ese recorte, lo que queda comprobado es lo que importa —los
# archivos que la doc manda abrir o pasar a un comando— y no hay falsos positivos que enseñen
# a ignorar este test.
CON_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")


def texto(doc: Path) -> str:
    return doc.read_text(encoding="utf-8")


def sin_placeholder(token: str) -> bool:
    return not PLACEHOLDER.search(token)


def limpiar(token: str) -> str:
    """Saca comillas, backticks y la puntuación que arrastra un token citado en prosa."""
    return token.strip("`\"'()[],;:").rstrip(".")


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.name)
def test_las_rutas_del_repo_que_nombra_la_doc_existen(doc: Path) -> None:
    """Un `helm/teleflow/values.yaml` que se renombró deja la doc mandando a la nada."""
    faltan = []
    for bruto in re.findall(r"[`\"']?([\w./-]+/[\w./-]+)[`\"']?", texto(doc)):
        token = limpiar(bruto)
        if not token.startswith(RAICES) or not sin_placeholder(token):
            continue
        if not CON_EXTENSION.search(token):
            continue
        if not (ROOT / token).exists():
            faltan.append(token)

    assert not faltan, (
        f"{doc.name} nombra rutas del repo que no existen: {sorted(set(faltan))}"
    )


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.name)
def test_los_archivos_que_la_doc_pasa_con_f_existen_desde_la_raiz(doc: Path) -> None:
    """El caso que motivó este test.

    `-f values-production.yaml` es válido como texto y falla como comando: el archivo está en
    `helm/teleflow/`. Quien copia y pega desde la raíz del repo —que es de donde se copia—
    recibe `Error: open values-production.yaml: no such file`. La ruta de un `-f` se resuelve
    desde donde se corre el comando, así que tiene que estar completa.
    """
    faltan = []
    for bruto in re.findall(r"(?:^|\s)(?:-f|--values)[=\s]+(\S+)", texto(doc), re.MULTILINE):
        token = limpiar(bruto).rstrip("\\")
        if not token or not sin_placeholder(token):
            continue
        if not (ROOT / token).exists():
            faltan.append(token)

    assert not faltan, (
        f"{doc.name} pasa con -f archivos que no existen desde la raíz del repo: "
        f"{sorted(set(faltan))}. Una ruta relativa a otra carpeta falla al copiar y pegar."
    )


def claves_de(datos: object, prefijo: str = "") -> set[str]:
    """Todas las rutas con punto de un YAML anidado, incluidos los nodos intermedios."""
    encontradas: set[str] = set()
    if isinstance(datos, dict):
        for clave, valor in datos.items():
            ruta = f"{prefijo}.{clave}" if prefijo else str(clave)
            encontradas.add(ruta)
            encontradas |= claves_de(valor, ruta)
    return encontradas


def es_mapa_libre(valores: object, clave: str) -> bool:
    """¿La clave cae dentro de un mapa que el chart deja vacío para que lo llene el usuario?

    `observabilidad.serviceMonitor.labels: {}` y `annotations: {}` existen justamente para que
    el organismo meta ahí sus propias claves, así que `--set ...labels.release=x` es correcto
    aunque `release` no figure en `values.yaml`. Sin esta excepción el test daría un falso
    positivo sobre el uso previsto del chart.
    """
    nodo: object = valores
    for parte in clave.split("."):
        if not isinstance(nodo, dict):
            return False
        if parte not in nodo:
            return nodo == {}
        nodo = nodo[parte]
    return False


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.name)
def test_las_claves_de_values_que_usa_la_doc_existen_en_el_chart(doc: Path) -> None:
    """Un `--set` a una clave que el chart ya no tiene es un no-op silencioso.

    Helm **no** avisa: acepta cualquier `--set`, así que renombrar un valor deja a la doc
    mandando una opción que no hace nada, y la instalación queda con el default sin que nadie
    se entere. Es el mismo modo de falla que un warning que no corta.
    """
    valores = yaml.safe_load(VALUES.read_text(encoding="utf-8"))
    disponibles = claves_de(valores)
    faltan = []
    for bruto in re.findall(r"--set\s+([\w.\[\]-]+)=", texto(doc)):
        # `tls[0].secretName` se comprueba hasta `tls`: el contenido de la lista es del usuario.
        clave = re.sub(r"\[\d+\].*$", "", bruto)
        if not clave or clave in disponibles or es_mapa_libre(valores, clave):
            continue
        faltan.append(bruto)

    assert not faltan, (
        f"{doc.name} usa --set con claves que no están en values.yaml: {sorted(set(faltan))}. "
        f"Helm las acepta igual y no hacen nada."
    )
