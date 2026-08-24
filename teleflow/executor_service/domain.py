"""Carga del dominio: merge de todos los flows registrados (versión latest).

El executor re-parsea el source con el mismo paquete teleflow.dsl, de modo
que el AST en memoria son siempre dataclasses tipadas. Cache con TTL corto;
el deploy de un flow se refleja en segundos sin reiniciar el servicio.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from prometheus_client import Counter, Gauge

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teleflow.common.logging import get_logger
from teleflow.dsl.ast_nodes import FlowFile, ProcessDef
from teleflow.dsl.parser import TeleFlowParser

log = get_logger(component="domain-loader")


# Un flow que no parsea desaparece del dominio: sus procesos y rules dejan de existir
# sin que ninguna instancia falle. Tiene que ser visible, no solo una línea de log.
DOMAIN_PARSE_FAILURES = Counter(
    "teleflow_domain_parse_failures_total",
    "Flows registrados que no parsean al cargar el dominio",
    ["flow_name"],
)
DOMAIN_BROKEN_FLOWS = Gauge(
    "teleflow_domain_broken_flows",
    "Flows del dominio actual que no se pudieron parsear",
)


@dataclass
class Domain:
    merged: FlowFile
    # process_name -> (flow_name, flow_version)
    process_index: dict[str, tuple[str, str]]
    # flows registrados que no parsean: su contenido NO está en `merged`
    broken_flows: list[str] = field(default_factory=list)


class DomainLoader:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession],
                 parser: TeleFlowParser, ttl_seconds: int = 30):
        self._sessionmaker = sessionmaker
        self._parser = parser
        self._ttl = ttl_seconds
        self._cache: Domain | None = None
        self._cached_at = 0.0
        self._parsed: dict[str, FlowFile] = {}  # checksum -> FlowFile

    async def load(self, force: bool = False) -> Domain:
        if not force and self._cache is not None \
                and time.monotonic() - self._cached_at < self._ttl:
            return self._cache

        from teleflow.common.models import FlowDefinition, FlowLatest

        merged = FlowFile()
        process_index: dict[str, tuple[str, str]] = {}
        broken_flows: list[str] = []
        async with self._sessionmaker() as session:
            latests = (await session.execute(select(FlowLatest))).scalars().all()
            for latest in latests:
                row = await session.scalar(
                    select(FlowDefinition).where(
                        FlowDefinition.name == latest.name,
                        FlowDefinition.version == latest.version,
                    )
                )
                if row is None:
                    continue
                flow = self._parse_cached(row.checksum, row.source, row.name)
                if flow is None:
                    broken_flows.append(row.name)
                    continue
                merged = merged.merge(flow)
                for proc_name in flow.processes:
                    process_index[proc_name] = (row.name, row.version)

        DOMAIN_BROKEN_FLOWS.set(len(broken_flows))
        if broken_flows:
            log.error("domain_degraded", broken_flows=broken_flows,
                      detail="sus procesos y rules no existen para el executor")
        self._cache = Domain(merged=merged, process_index=process_index,
                             broken_flows=broken_flows)
        self._cached_at = time.monotonic()
        return self._cache

    def _parse_cached(self, csum: str, source: str, name: str) -> FlowFile | None:
        if csum in self._parsed:
            return self._parsed[csum]
        try:
            flow = self._parser.parse(source)
        except Exception as exc:  # flow corrupto registrado: no rompe el dominio
            log.error("domain_parse_failed", flow_name=name, error=str(exc))
            DOMAIN_PARSE_FAILURES.labels(name).inc()
            return None
        self._parsed[csum] = flow
        if len(self._parsed) > 200:
            self._parsed.clear()
        return flow

    async def find_process(self, process_name: str) -> tuple[ProcessDef, str, str] | None:
        domain = await self.load()
        proc = domain.merged.processes.get(process_name)
        if proc is None:
            return None
        flow_name, version = domain.process_index[process_name]
        return proc, flow_name, version
