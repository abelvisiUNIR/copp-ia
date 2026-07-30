"""Contrato entre los dashboards de Grafana y las métricas que el código publica.

Un dashboard roto no falla nada: Grafana muestra el panel vacío y parece que no hay
trabajo pendiente. Estos tests fijan las formas en que se rompía en silencio — métricas que no
existen, provisión que el volumen de Grafana tapaba, y ahora también que haya **dos copias** de
los dashboards desincronizándose.

Los dashboards viven dentro del chart (`helm/teleflow/dashboards/`) y no en `observability/`
porque Helm solo puede leer archivos de adentro del chart: si estuvieran afuera, el chart
necesitaría su propia copia. Una sola fuente, dos consumidores — la imagen de Grafana del
compose y el ConfigMap que genera el chart.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS = ROOT / "helm" / "teleflow" / "dashboards"
CONFIGMAP = ROOT / "helm" / "teleflow" / "templates" / "observabilidad.yaml"
PROVIDER = ROOT / "observability" / "grafana" / "provisioning" / "dashboards" / "provider.yml"
GRAFANA_DOCKERFILE = ROOT / "observability" / "grafana.Dockerfile"

# Sufijos que Prometheus agrega a un histograma; la métrica declarada es la base.
SUFIJOS_HISTOGRAMA = ("_bucket", "_sum", "_count")


def dashboards() -> list[Path]:
    return sorted(DASHBOARDS.glob("*.json"))


def metricas_declaradas() -> set[str]:
    """Nombres de métrica que el código registra en Prometheus."""
    nombres: set[str] = set()
    for py in (ROOT / "teleflow").rglob("*.py"):
        nombres |= set(re.findall(r'"(teleflow_[a-z0-9_]+)"', py.read_text(encoding="utf-8")))
    return nombres


def metricas_usadas(dashboard: Path) -> set[str]:
    data = json.loads(dashboard.read_text(encoding="utf-8"))
    exprs = [t["expr"] for p in data["panels"] for t in p.get("targets", [])]
    return {m for expr in exprs for m in re.findall(r"teleflow_[a-z0-9_]+", expr)}


def test_hay_dashboards_versionados():
    assert dashboards(), f"no hay ningún dashboard en {DASHBOARDS}"


def test_no_hay_una_segunda_copia_de_los_dashboards():
    """Dos copias se desincronizan sin que nada avise: el panel que ve el organismo deja de ser
    el que ve el equipo, y no hay error que lo delate."""
    assert not (ROOT / "observability" / "grafana" / "dashboards").exists(), (
        "volvió a aparecer una copia de los dashboards en observability/"
    )


def test_los_dos_consumidores_leen_la_misma_carpeta():
    """El compose por el COPY del Dockerfile; el cluster por el ConfigMap del chart."""
    dockerfile = GRAFANA_DOCKERFILE.read_text(encoding="utf-8")
    plantilla = CONFIGMAP.read_text(encoding="utf-8")

    assert "helm/teleflow/dashboards" in dockerfile, (
        "la imagen de Grafana del compose dejó de leer los dashboards del chart"
    )
    assert 'Files.Glob "dashboards/*.json"' in plantilla, (
        "el ConfigMap dejó de tomar los dashboards de la carpeta del chart"
    )


@pytest.mark.parametrize("dashboard", dashboards(), ids=lambda p: p.stem)
def test_cada_dashboard_es_json_valido_con_uid_y_paneles(dashboard: Path):
    data = json.loads(dashboard.read_text(encoding="utf-8"))

    assert data.get("uid"), f"{dashboard.name} sin uid: Grafana lo duplicaría en cada deploy"
    assert data.get("title")
    assert data.get("panels"), f"{dashboard.name} sin paneles"


def test_los_uid_no_se_repiten_entre_dashboards():
    uids = [json.loads(d.read_text(encoding="utf-8"))["uid"] for d in dashboards()]

    assert len(uids) == len(set(uids)), f"uid duplicado entre dashboards: {uids}"


@pytest.mark.parametrize("dashboard", dashboards(), ids=lambda p: p.stem)
def test_los_paneles_solo_usan_metricas_que_el_codigo_publica(dashboard: Path):
    """Un typo en el nombre de la métrica deja el panel vacío, sin error visible."""
    declaradas = metricas_declaradas()

    for usada in metricas_usadas(dashboard):
        base = usada
        for sufijo in SUFIJOS_HISTOGRAMA:
            if base.endswith(sufijo):
                base = base[: -len(sufijo)]
        assert base in declaradas, (
            f"{dashboard.name} consulta '{usada}', que ningún servicio publica"
        )


def test_la_provision_apunta_a_donde_la_imagen_copia_los_dashboards():
    """El volumen grafana-data monta /var/lib/grafana y tapa lo que traiga la imagen: los
    dashboards viven fuera de ahí, si no un dashboard nuevo nunca llega a una instalación
    existente (el volumen viejo gana)."""
    provider = PROVIDER.read_text(encoding="utf-8")
    dockerfile = GRAFANA_DOCKERFILE.read_text(encoding="utf-8")

    path = re.search(r"^\s*path:\s*(\S+)", provider, re.MULTILINE)
    copia = re.search(r"^COPY\s+helm/teleflow/dashboards\s+(\S+)", dockerfile, re.MULTILINE)

    assert path and copia, "no se pudo leer el path de provisión o el COPY de la imagen"
    assert path.group(1) == copia.group(1), (
        f"la provisión lee {path.group(1)} pero la imagen copia a {copia.group(1)}"
    )
    assert not path.group(1).startswith("/var/lib/grafana"), (
        "el volumen grafana-data tapa /var/lib/grafana"
    )
