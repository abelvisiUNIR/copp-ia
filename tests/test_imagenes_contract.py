"""Que la capa de datos del compose y la del chart sean la misma.

Postgres, Redis y RabbitMQ están declarados **dos veces**: en `docker-compose.yml` (lo que
prueban los e2e) y en `helm/teleflow/values.yaml` (lo que se instala en el cluster). Los
`values` traen el comentario "si cambia una, cambia la otra", que es exactamente la clase de
regla que el próximo cambio olvida — y el olvido no hace ruido: los dos lados siguen
levantando, cada uno con su versión, y la divergencia aparece recién cuando algo se comporta
distinto en producción que en los tests.

Es el mismo hueco que ya cierran `test_observability_contract.py` (dashboards) y
`test_alertas.py` (reglas), con la diferencia de que acá no se puede tener una sola fuente:
compose y Helm son formatos distintos. Si no se puede unificar el archivo, se fija la igualdad
con un test.

Estático, sin docker y sin red. Que las imágenes **existan** en el registry es otro chequeo,
que depende de una dependencia externa y no vive en pytest.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
VALUES = ROOT / "helm" / "teleflow" / "values.yaml"
STATEFULSETS = ROOT / "helm" / "teleflow" / "templates" / "datos.yaml"

# Los tres servicios que están declarados en los dos lados. El nombre coincide en compose y en
# values a propósito; si alguno se renombra, este test lo dice antes que la divergencia.
SERVICIOS_DE_DATOS = ("postgres", "redis", "rabbitmq")


def bloques(texto: str, sangria: str) -> dict[str, str]:
    """Mapea cada clave de ese nivel de sangría a su cuerpo, cortando en la siguiente."""
    partes = re.split(rf"^{sangria}([\w-]+):\s*$", texto, flags=re.MULTILINE)[1:]
    return dict(zip(partes[::2], partes[1::2]))


def imagen(cuerpo: str, sangria: str) -> str | None:
    hallazgo = re.search(rf"^{sangria}image:\s*(\S+)", cuerpo, re.MULTILINE)
    return hallazgo.group(1).strip("\"'") if hallazgo else None


def imagenes_del_compose() -> dict[str, str]:
    cuerpo = COMPOSE.read_text(encoding="utf-8").split("\nservices:\n", 1)[1]
    encontradas = {
        nombre: imagen(bloque, "    ") for nombre, bloque in bloques(cuerpo, "  ").items()
    }
    return {nombre: img for nombre, img in encontradas.items() if img}


def imagenes_del_chart() -> dict[str, str]:
    texto = VALUES.read_text(encoding="utf-8")
    encontradas = {
        nombre: imagen(bloque, "  ") for nombre, bloque in bloques(texto, "").items()
    }
    return {nombre: img for nombre, img in encontradas.items() if img}


def test_los_tres_servicios_de_datos_estan_declarados_en_los_dos_lados():
    """Si uno desaparece de un lado, el test de igualdad de abajo no tendría nada que comparar
    y pasaría en verde — otro test vacuo."""
    compose = imagenes_del_compose()
    chart = imagenes_del_chart()

    faltan_en_compose = [s for s in SERVICIOS_DE_DATOS if s not in compose]
    faltan_en_chart = [s for s in SERVICIOS_DE_DATOS if s not in chart]

    assert not faltan_en_compose, f"sin imagen en docker-compose.yml: {faltan_en_compose}"
    assert not faltan_en_chart, f"sin imagen en values.yaml: {faltan_en_chart}"


@pytest.mark.parametrize("servicio", SERVICIOS_DE_DATOS)
def test_la_capa_de_datos_usa_la_misma_imagen_en_el_compose_y_en_el_chart(servicio: str):
    """Antes esto eran subcharts de Bitnami mientras el compose usaba las imágenes oficiales:
    los e2e probaban una capa de datos que producción no usaba. Se unificó a propósito, y sin
    este test la unificación dura hasta el primer bump de un solo lado."""
    en_compose = imagenes_del_compose()[servicio]
    en_chart = imagenes_del_chart()[servicio]

    assert en_compose == en_chart, (
        f"{servicio}: el compose levanta {en_compose} y el chart instala {en_chart} — "
        f"los e2e dejaron de probar la capa de datos que se despliega"
    )


@pytest.mark.parametrize("servicio", SERVICIOS_DE_DATOS)
def test_el_statefulset_toma_la_imagen_de_values(servicio: str):
    """Si la plantilla hardcodea la imagen, `values.yaml` queda de adorno: el test de arriba
    compararía dos strings que ya no deciden nada, y el organismo que sobreescribe el valor no
    obtiene lo que pidió."""
    plantilla = STATEFULSETS.read_text(encoding="utf-8")

    assert f".Values.{servicio}.image" in plantilla, (
        f"el StatefulSet de {servicio} dejó de tomar la imagen de values.yaml"
    )


@pytest.mark.parametrize("servicio", SERVICIOS_DE_DATOS)
def test_las_imagenes_de_datos_estan_ancladas_a_una_version(servicio: str):
    """Un tag mutable hace que `helm upgrade` reporte éxito sin rotar los pods: el spec
    renderizado es byte a byte el mismo, así que Kubernetes no tiene motivo para volver a bajar
    la imagen. Y en el compose, dos máquinas con el mismo repo corren versiones distintas."""
    referencia = imagenes_del_chart()[servicio]
    _, _, tag = referencia.rpartition(":")

    assert tag and tag != referencia, f"{servicio}: {referencia} no fija tag (implica 'latest')"
    assert tag != "latest", f"{servicio}: tag mutable 'latest' en {referencia}"
