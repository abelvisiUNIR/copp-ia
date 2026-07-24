"""CLI tflow — interfaz de línea de comandos contra el api-gateway.

Configuración por entorno:
  TELEFLOW_URL      (default http://localhost:8000)
  TELEFLOW_API_KEY  (default dev-key-change-me)

Comandos:
  tflow validate <archivo.tflow>
  tflow deploy <archivo.tflow> --name venta --version 1.0.0
  tflow flows
  tflow execute <flow> --payload '{"k":"v"}'
  tflow status <instance_id>
  tflow signal <instance_id> --step aprobacion --signal approve --actor juan
  tflow compose <nombre> --description "..."
  tflow drafts
  tflow approve <draft_id> --version 1.0.0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx


def _client() -> httpx.Client:
    base_url = os.environ.get("TELEFLOW_URL", "http://localhost:8000")
    api_key = os.environ.get("TELEFLOW_API_KEY", "dev-key-change-me")
    return httpx.Client(
        base_url=base_url,
        headers={"X-TeleFlow-API-Key": api_key},
        timeout=60,
    )


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _die(response: httpx.Response) -> None:
    try:
        _print(response.json())
    except ValueError:
        print(response.text)
    sys.exit(1)


def cmd_validate(args: argparse.Namespace) -> None:
    source = Path(args.file).read_text(encoding="utf-8")
    with _client() as client:
        response = client.post("/parse", json={"source": source, "name": args.file})
    if response.status_code >= 400:
        _die(response)
    data = response.json()
    print("✓ válido" if data["valid"] else "✗ inválido")
    for issue in data["issues"]:
        print(f"  [{issue['level']}] {issue['message']}")
    if not data["valid"]:
        sys.exit(1)


def cmd_deploy(args: argparse.Namespace) -> None:
    source = Path(args.file).read_text(encoding="utf-8")
    name = args.name or Path(args.file).stem
    with _client() as client:
        response = client.post(f"/flows/{name}", json={
            "source": source, "version": args.version,
            "description": args.description,
        })
    if response.status_code >= 400:
        _die(response)
    _print(response.json())


def cmd_flows(args: argparse.Namespace) -> None:
    with _client() as client:
        response = client.get("/flows")
    if response.status_code >= 400:
        _die(response)
    _print(response.json())


def cmd_execute(args: argparse.Namespace) -> None:
    payload = json.loads(args.payload) if args.payload else {}
    with _client() as client:
        response = client.post("/execute", json={
            "flow_name": args.flow, "version": args.version,
            "payload": payload, "correlation_id": args.correlation_id,
        })
    if response.status_code >= 400:
        _die(response)
    _print(response.json())


def cmd_status(args: argparse.Namespace) -> None:
    with _client() as client:
        response = client.get(f"/instances/{args.instance_id}")
    if response.status_code >= 400:
        _die(response)
    _print(response.json())


def cmd_signal(args: argparse.Namespace) -> None:
    data = json.loads(args.data) if args.data else {}
    with _client() as client:
        response = client.post(f"/instances/{args.instance_id}/signal", json={
            "step_name": args.step, "signal": args.signal,
            "actor_id": args.actor, "signal_data": data,
        })
    if response.status_code >= 400:
        _die(response)
    _print(response.json())


def cmd_compose(args: argparse.Namespace) -> None:
    with _client() as client:
        response = client.post("/compose", json={
            "name": args.name, "description": args.description,
        })
    if response.status_code >= 400:
        _die(response)
    data = response.json()
    print(f"draft_id: {data['draft_id']}")
    print(data["source"])


def cmd_drafts(args: argparse.Namespace) -> None:
    with _client() as client:
        response = client.get("/drafts")
    if response.status_code >= 400:
        _die(response)
    _print(response.json())


def cmd_approve(args: argparse.Namespace) -> None:
    with _client() as client:
        response = client.post(f"/drafts/{args.draft_id}/approve", json={
            "version": args.version, "actor_id": args.actor,
        })
    if response.status_code >= 400:
        _die(response)
    _print(response.json())


def main() -> None:
    # Forzar UTF-8 en la salida: en consolas Windows (cp1252) imprimir ✓/✗ crashea.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="tflow",
                                     description="TeleFlow CLI — Business & Software as Code")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="valida un archivo .tflow")
    p.add_argument("file")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("deploy", help="valida y registra un flow")
    p.add_argument("file")
    p.add_argument("--name", default=None)
    p.add_argument("--version", required=True)
    p.add_argument("--description", default="")
    p.set_defaults(func=cmd_deploy)

    p = sub.add_parser("flows", help="lista los flows registrados")
    p.set_defaults(func=cmd_flows)

    p = sub.add_parser("execute", help="dispara un proceso")
    p.add_argument("flow")
    p.add_argument("--version", default="latest")
    p.add_argument("--payload", default="{}")
    p.add_argument("--correlation-id", default=None)
    p.set_defaults(func=cmd_execute)

    p = sub.add_parser("status", help="estado de una instancia")
    p.add_argument("instance_id")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("signal", help="envía señal a un human_task")
    p.add_argument("instance_id")
    p.add_argument("--step", required=True)
    p.add_argument("--signal", required=True)
    p.add_argument("--actor", default=None)
    p.add_argument("--data", default="{}")
    p.set_defaults(func=cmd_signal)

    p = sub.add_parser("compose", help="genera borrador .tflow con IA")
    p.add_argument("name")
    p.add_argument("--description", required=True)
    p.set_defaults(func=cmd_compose)

    p = sub.add_parser("drafts", help="lista borradores")
    p.set_defaults(func=cmd_drafts)

    p = sub.add_parser("approve", help="aprueba y despliega un borrador")
    p.add_argument("draft_id")
    p.add_argument("--version", required=True)
    p.add_argument("--actor", default="cli")
    p.set_defaults(func=cmd_approve)

    args = parser.parse_args()
    try:
        args.func(args)
    except httpx.ConnectError:
        print(f"No se pudo conectar a {os.environ.get('TELEFLOW_URL', 'http://localhost:8000')}",
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
