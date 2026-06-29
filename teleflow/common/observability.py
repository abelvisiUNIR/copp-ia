"""Health, readiness y métricas Prometheus para todos los servicios.

Cada servicio expone:
  GET /health  — liveness
  GET /ready   — readiness (opcionalmente verifica dependencias)
  GET /metrics — formato Prometheus
"""
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "teleflow_http_requests_total",
    "Total de requests HTTP",
    ["service", "method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "teleflow_http_request_seconds",
    "Latencia de requests HTTP",
    ["service", "method", "path"],
)

ReadyCheck = Callable[[], Awaitable[bool]]


def setup_observability(
    app: FastAPI,
    service_name: str,
    ready_check: ReadyCheck | None = None,
) -> None:
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        if path not in ("/metrics", "/health", "/ready"):
            HTTP_REQUESTS.labels(service_name, request.method, path, response.status_code).inc()
            HTTP_LATENCY.labels(service_name, request.method, path).observe(
                time.perf_counter() - start
            )
        return response

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": service_name}

    @app.get("/ready", include_in_schema=False)
    async def ready() -> Response:
        if ready_check is not None:
            try:
                ok = await ready_check()
            except Exception:
                ok = False
            if not ok:
                return Response(content='{"status":"not_ready"}', status_code=503,
                                media_type="application/json")
        return Response(content='{"status":"ready"}', media_type="application/json")

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
