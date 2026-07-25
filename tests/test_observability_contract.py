"""Contrato entre los dashboards de Grafana y las métricas que el código publica.

Un dashboard roto no falla nada: Grafana muestra el panel vacío y parece que no hay
trabajo pendiente. Estos tests fijan las dos formas en que se rompía en silencio —
métricas que no existen, y provisión que el volumen de Grafana tapaba.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DASHBOARDS = ROOT / "observability" / "grafana" / "dashboards"
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
    assert dashboards(), "no hay ningún dashboard en observability/grafana/dashboards"


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
    copia = re.search(r"^COPY\s+grafana/dashboards\s+(\S+)", dockerfile, re.MULTILINE)

    assert path and copia, "no se pudo leer el path de provisión o el COPY de la imagen"
    assert path.group(1) == copia.group(1), (
        f"la provisión lee {path.group(1)} pero la imagen copia a {copia.group(1)}"
    )
    assert not path.group(1).startswith("/var/lib/grafana"), (
        "el volumen grafana-data tapa /var/lib/grafana"
    )
