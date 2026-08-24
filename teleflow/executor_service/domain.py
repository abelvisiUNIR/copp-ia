"""Carga del dominio: merge de todos los flows registrados (versión latest).

El executor re-parsea el source con el mismo paquete teleflow.dsl, de modo
que el AST en memoria son siempre dataclasses tipadas. Cache con TTL corto;
el deploy de un flow se refleja en segundos sin reiniciar el servicio.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teleflow.common.logging import get_logger
from teleflow.dsl.ast_nodes import FlowFile, ProcessDef
from teleflow.dsl.parser import TeleFlowParser

log = get_logger(component="domain-loader")


@dataclass
class Domain:
    merged: FlowFile
    # process_name -> (flow_name, flow_version)
    process_index: dict[str, tuple[str, str]]


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
                    continue
                merged = merged.merge(flow)
                for proc_name in flow.processes:
                    process_index[proc_name] = (row.name, row.version)

        self._cache = Domain(merged=merged, process_index=process_index)
        self._cached_at = time.monotonic()
        return self._cache

    def _parse_cached(self, csum: str, source: str, name: str) -> FlowFile | None:
        if csum in self._parsed:
            return self._parsed[csum]
        try:
            flow = self._parser.parse(source)
        except Exception as exc:  # flow corrupto registrado: no rompe el dominio
            log.error("domain_parse_failed", flow_name=name, error=str(exc))
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
