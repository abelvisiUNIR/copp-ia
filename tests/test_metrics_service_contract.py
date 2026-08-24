"""Que los gauges de negocio los publique un solo proceso, y que eso esté fijado.

La garantía no la sostiene el código del colector: la sostiene la topología del despliegue. Un
componente con una sola réplica no necesita coordinarse con nadie. Por eso lo que hay que
proteger con tests es justamente eso — que el colector viva en `metrics-service`, que
`metrics-service` esté en 1 réplica, y que el executor (que corre con 3) no lo arranque.

Sale de un bug medido en un cluster real: con el colector en el executor, los tres pods
publicaban el valor absoluto y el dashboard —que suma entre pods— leía 3× todo el negocio. El
primer intento de arreglo fue un advisory lock por ciclo, y no alcanzó: dos ciclos que no se
solapan en el tiempo no se excluyen entre sí. Estos tests fijan la solución que sí funciona,
para que no se deshaga sin querer.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
VALUES = ROOT / "helm" / "teleflow" / "values.yaml"


def test_el_executor_no_publica_los_gauges_de_negocio():
    """El executor corre con 3 réplicas: si vuelve a arrancar el colector, vuelve el 3×."""
    fuente = (ROOT / "teleflow" / "executor_service" / "main.py").read_text(encoding="utf-8")

    assert "BusinessMetricsCollector" not in fuente, (
        "el executor volvió a arrancar el colector de métricas de negocio. Corre con varias "
        "réplicas y los gauges llevan el valor absoluto: el dashboard va a leer N× el negocio. "
        "El colector va en metrics-service, que corre en 1 réplica."
    )


def test_el_metrics_service_arranca_el_colector():
    fuente = (ROOT / "teleflow" / "metrics_service" / "main.py").read_text(encoding="utf-8")

    assert "BusinessMetricsCollector" in fuente
    assert "business_metrics.start()" in fuente


def test_el_chart_fija_metrics_service_en_una_replica():
    """Escalarlo a 2 reintroduce el bug exacto, sin ningún síntoma visible."""
    bloque = re.search(
        r"^  metrics-service:\n((?:    .+\n|\n)+)", VALUES.read_text(encoding="utf-8"),
        re.MULTILINE)
    assert bloque, "metrics-service no está declarado en los values del chart"

    replicas = re.search(r"replicas:\s*(\d+)", bloque.group(1))
    assert replicas, "metrics-service no declara replicas"
    assert replicas.group(1) == "1", (
        f"metrics-service está en {replicas.group(1)} réplicas. Cada réplica publica el valor "
        f"absoluto y el dashboard suma entre pods: el negocio se leería "
        f"{replicas.group(1)}× sin que nada falle."
    )


def test_el_compose_tiene_el_metrics_service():
    """Si falta en el compose, dev y CI no miden nada de negocio y nadie se entera."""
    compose = COMPOSE.read_text(encoding="utf-8")

    assert re.search(r"^  metrics-service:$", compose, re.MULTILINE), (
        "metrics-service no está en docker-compose.yml: los gauges de negocio no se publicarían "
        "en dev ni en CI, y los e2e que los leen quedarían midiendo un stack que no los produce."
    )


def test_prometheus_scrapea_el_metrics_service():
    """Un servicio que publica métricas y no está en el scrape config es un panel vacío.

    Y "No data" en un panel de backlog se lee igual que "no hay trabajo pendiente", que es la
    lectura tranquilizadora equivocada. Pasó al mover el colector: el servicio nuevo quedó fuera
    de la lista de targets y los e2e siguieron verdes un rato con las series viejas que
    Prometheus todavía retenía.
    """
    prom = (ROOT / "observability" / "prometheus.yml").read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")

    puerto = re.search(r"teleflow\.metrics_service\.main:app --host \S+ --port (\d+)", compose)
    assert puerto, "no se pudo leer el puerto de metrics-service en docker-compose.yml"

    assert f"metrics-service:{puerto.group(1)}" in prom, (
        f"metrics-service:{puerto.group(1)} no está en los targets de Prometheus: los gauges de "
        f"negocio no se scrapean y los paneles quedan sin datos."
    )
