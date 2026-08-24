#!/usr/bin/env python3
"""Verifica que las imágenes de contenedor que el repo referencia todavía existan.

Motivo: las imágenes de los subcharts de Bitnami fueron **retiradas de Docker Hub** y rompieron
el chart sin que nadie tocara un archivo. `helm dependency update` seguía diciendo éxito, el
lint pasaba y los tests pasaban: el fallo aparecía recién cuando un pod intentaba bajar la
imagen. Un artefacto que no cambió dejó de funcionar solo, y no había con qué enterarse.

Por eso esto **no** corre en cada push: el modo de falla no tiene commit asociado, así que un
disparador por `push` no se enteraría nunca. Corre programado (`.github/workflows/imagenes.yml`).
La mitad determinista —que las referencias estén bien formadas y que compose y chart coincidan—
sí gatea los merges, pero desde `tests/test_imagenes_contract.py`, sin tocar la red.

Uso:
    python scripts/verificar_imagenes.py            # verifica contra el registry
    python scripts/verificar_imagenes.py --listar   # solo enumera, sin red

Salida: 0 todo existe · 1 alguna no existe · 2 no se pudo verificar (registry inalcanzable).
El 1 y el 2 se distinguen a propósito: "la imagen no está" y "no pude preguntar" piden cosas
distintas, y confundirlos entrena a ignorar la alerta.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Carpetas con dependencias de terceros: sus Dockerfiles no son nuestros.
IGNORADAS = {"node_modules", ".venv", "venv", ".git", "dist", "build"}

# El organismo publica las imágenes de la plataforma en su propio registry; el valor por defecto
# es un placeholder que **no existe a propósito** (ADR-005, instancia por organismo). Se excluye
# por una regla nombrada y no por un `try/except` que taparía además lo que no está previsto.
REGISTRY_PLACEHOLDER = "registry.example.com"

INTENTOS = 3
ESPERA_ENTRE_INTENTOS = 5.0


class Estado(str, Enum):
    EXISTE = "existe"
    NO_EXISTE = "NO EXISTE"
    NO_SE_PUDO = "no se pudo verificar"


@dataclass(frozen=True)
class Referencia:
    imagen: str
    origen: str


def _texto(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _relativo(ruta: Path) -> str:
    """Ruta legible para el reporte. Un Dockerfile de afuera del repo se nombra entero en vez
    de reventar: quien lee el fallo necesita saber qué archivo lo declara, siempre."""
    try:
        return ruta.relative_to(ROOT).as_posix()
    except ValueError:
        return ruta.as_posix()


def dockerfiles() -> list[Path]:
    """Todos los Dockerfile del repo, sin lista escrita a mano."""
    encontrados = [
        *ROOT.rglob("Dockerfile"),
        *ROOT.rglob("*.Dockerfile"),
    ]
    return sorted(
        ruta for ruta in encontrados
        if not IGNORADAS & set(ruta.relative_to(ROOT).parts)
    )


def referencias_de_dockerfile(ruta: Path) -> list[Referencia]:
    """Las bases de cada `FROM`, salteando las etapas internas de un build multi-stage.

    En `FROM x AS build` + `FROM build`, la segunda no es una imagen del registry: es la etapa
    de arriba. Tratarla como imagen daría un "no existe" falso, que es la forma más rápida de
    que nadie mire más esta alerta.
    """
    texto = _texto(ruta)
    etapas = {m.lower() for m in re.findall(r"^FROM\s+\S+\s+AS\s+(\S+)", texto,
                                            re.MULTILINE | re.IGNORECASE)}
    hallazgos = re.findall(r"^FROM\s+(\S+)", texto, re.MULTILINE | re.IGNORECASE)

    return [
        Referencia(imagen, f"{_relativo(ruta)} (FROM)")
        for imagen in hallazgos
        if imagen.lower() not in etapas and "${" not in imagen
    ]


def referencias_del_compose() -> list[Referencia]:
    ruta = ROOT / "docker-compose.yml"
    cuerpo = _texto(ruta).split("\nservices:\n", 1)[1]
    hallazgos = re.findall(r"^    image:\s*(\S+)", cuerpo, re.MULTILINE)

    return [Referencia(img.strip("\"'"), _relativo(ruta)) for img in hallazgos]


def referencias_del_chart() -> list[Referencia]:
    """La capa de datos (`postgres.image`, …) y la imagen de la plataforma (`repository`/`tag`)."""
    ruta = ROOT / "helm" / "teleflow" / "values.yaml"
    texto = _texto(ruta)
    origen = _relativo(ruta)

    encontradas = [
        Referencia(img.strip("\"'"), origen)
        for img in re.findall(r"^  image:\s*(\S+)", texto, re.MULTILINE)
    ]
    repos = re.findall(r"^  repository:\s*(\S+)\n\s*(?:pullPolicy:.*\n\s*)?tag:\s*(\S+)",
                       texto, re.MULTILINE)
    encontradas += [
        Referencia(f"{repo.strip(chr(34))}:{tag.strip(chr(34))}", origen) for repo, tag in repos
    ]
    return encontradas


def referencias() -> list[Referencia]:
    """Todas las referencias del repo, deduplicadas y ordenadas."""
    todas: list[Referencia] = []
    for ruta in dockerfiles():
        todas += referencias_de_dockerfile(ruta)
    todas += referencias_del_compose()
    todas += referencias_del_chart()

    vistas: dict[str, Referencia] = {}
    for ref in todas:
        vistas.setdefault(ref.imagen, ref)
    return sorted(vistas.values(), key=lambda r: r.imagen)


def es_del_organismo(imagen: str) -> bool:
    """Las imágenes que publica cada instalación no se pueden verificar desde acá."""
    return imagen.startswith(REGISTRY_PLACEHOLDER)


def consultar(imagen: str) -> Estado:
    """`docker manifest inspect` sin bajar la imagen: pregunta al registry por el manifest.

    Distingue "el registry contestó que no está" de "no pude hablar con el registry". No es una
    sutileza: reportar como faltante lo que en realidad no se pudo consultar es una alarma falsa,
    y unas pocas alcanzan para que nadie vuelva a mirar esta alerta.
    """
    ultimo = ""
    for intento in range(1, INTENTOS + 1):
        completado = subprocess.run(
            ["docker", "manifest", "inspect", imagen],
            capture_output=True, text=True, timeout=120,
        )
        if completado.returncode == 0:
            return Estado.EXISTE

        ultimo = (completado.stderr or completado.stdout).strip().lower()

        # El rate limit anónimo de Docker Hub se resetea en horas: reintentar en segundos solo
        # gasta tiempo y consume más cuota. Se corta acá, y el mensaje dice qué hacer.
        if "toomanyrequests" in ultimo or "rate limit" in ultimo:
            print(f"    rate limit del registry al consultar {imagen}: autenticar con "
                  f"DOCKERHUB_USER/DOCKERHUB_TOKEN", file=sys.stderr)
            return Estado.NO_SE_PUDO

        if any(pista in ultimo for pista in
               ("not found", "no such manifest", "manifest unknown", "unauthorized",
                "does not exist", "requested access to the resource is denied")):
            return Estado.NO_EXISTE

        if intento < INTENTOS:
            time.sleep(ESPERA_ENTRE_INTENTOS)

    print(f"    último error al consultar {imagen}: {ultimo[:200]}", file=sys.stderr)
    return Estado.NO_SE_PUDO


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listar", action="store_true",
                        help="enumera las referencias y sale, sin consultar el registry")
    args = parser.parse_args()

    refs = referencias()

    # Un verificador que no encuentra nada que verificar sale con 0 y **parece** que todo está
    # bien: exactamente la falla que este script existe para detectar, una capa más arriba.
    if not refs:
        print("ERROR: no se encontró ninguna referencia de imagen — el enumerador está roto",
              file=sys.stderr)
        return 2

    if args.listar:
        for ref in refs:
            marca = " (del organismo, no se verifica)" if es_del_organismo(ref.imagen) else ""
            print(f"{ref.imagen}{marca}\n    <- {ref.origen}")
        return 0

    faltantes: list[Referencia] = []
    dudosas: list[Referencia] = []

    for ref in refs:
        if es_del_organismo(ref.imagen):
            print(f"[{'--':^21}] {ref.imagen}  (del organismo, no se verifica)")
            continue

        estado = consultar(ref.imagen)
        detalle = "" if estado is Estado.EXISTE else f"  <- {ref.origen}"
        print(f"[{estado.value:^21}] {ref.imagen}{detalle}")

        if estado is Estado.NO_EXISTE:
            faltantes.append(ref)
        elif estado is Estado.NO_SE_PUDO:
            dudosas.append(ref)

    if faltantes:
        print(f"\nNO EXISTEN {len(faltantes)} imágenes referenciadas:", file=sys.stderr)
        for ref in faltantes:
            print(f"  {ref.imagen}  <- {ref.origen}", file=sys.stderr)
        return 1

    if dudosas:
        print(f"\nNo se pudo verificar {len(dudosas)} (registry inalcanzable tras "
              f"{INTENTOS} intentos). Esto NO dice que falten.", file=sys.stderr)
        return 2

    print(f"\nLas {len(refs)} referencias existen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
