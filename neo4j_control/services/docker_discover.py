"""Discover Neo4j containers managed by this app and other Docker Neo4j on the host."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any

from neo4j_control.models import Neo4jInstance
from neo4j_control.services.docker_neo4j import Neo4jDockerService, docker_available


@dataclass
class DockerNeo4jView:
    name: str
    status: str
    bolt_uri: str | None
    http_uri: str | None
    image: str | None
    managed: bool  # True = in our registry / compose stacks
    container_id: str | None = None
    can_start: bool = False
    detail: str = ""
    databases_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _docker_ps_neo4j() -> list[dict[str, Any]]:
    if not shutil.which("docker"):
        return []
    try:
        proc = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "ancestor=neo4j",
                "--format",
                "{{json .}}",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        # Broader filter: name/image containing neo4j
        try:
            proc = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        if proc.returncode != 0:
            return []
        rows = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            image = str(row.get("Image") or "")
            names = str(row.get("Names") or "")
            if "neo4j" in image.lower() or "neo4j" in names.lower():
                rows.append(row)
        return rows

    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _parse_bolt_from_ports(ports: str) -> str | None:
    # e.g. "0.0.0.0:7687->7687/tcp, 7474/tcp"
    for part in ports.split(","):
        part = part.strip()
        if "7687" in part and "->" in part:
            left = part.split("->", 1)[0]
            if ":" in left:
                host_port = left.rsplit(":", 1)[-1]
                if host_port.isdigit():
                    return f"bolt://127.0.0.1:{host_port}"
    return None


def discover_docker_neo4j(svc: Neo4jDockerService) -> tuple[list[DockerNeo4jView], list[str]]:
    notes: list[str] = []
    ok, detail = docker_available()
    views: list[DockerNeo4jView] = []

    managed: list[Neo4jInstance] = []
    try:
        managed = svc.list_instances() if ok else svc.registry.list()
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Registry list issue: {exc}")
        managed = svc.registry.list()

    managed_ports = {i.bolt_port for i in managed}
    managed_names = {i.name for i in managed}

    for inst in managed:
        can_start = ok and inst.status in {"defined", "stopped", "error", "unknown"}
        views.append(
            DockerNeo4jView(
                name=inst.name,
                status=inst.status,
                bolt_uri=inst.bolt_uri,
                http_uri=inst.http_uri,
                image=inst.image,
                managed=True,
                can_start=can_start,
                detail="Managed by Neo4j Control (Compose stack)",
            )
        )

    if not ok:
        notes.append(f"Docker not available: {detail}. Showing registry definitions only.")
        return views, notes

    for row in _docker_ps_neo4j():
        names = str(row.get("Names") or row.get("names") or "")
        name = names.split(",")[0].strip() or str(row.get("ID", ""))[:12]
        # Skip if clearly one of ours (compose project neo4j-<name>)
        short = name
        for prefix in ("neo4j-",):
            if short.startswith(prefix):
                short = short[len(prefix) :]
                if short.endswith("-neo4j"):
                    short = short[: -len("-neo4j")]
        if short in managed_names or name in managed_names:
            continue
        ports = str(row.get("Ports") or "")
        bolt = _parse_bolt_from_ports(ports)
        # Avoid double-count by port
        if bolt:
            try:
                port = int(bolt.rsplit(":", 1)[-1])
                if port in managed_ports:
                    continue
            except ValueError:
                pass
        state = str(row.get("State") or row.get("Status") or "unknown").lower()
        status = "running" if state.startswith("running") or "up" in state else "stopped"
        views.append(
            DockerNeo4jView(
                name=name,
                status=status,
                bolt_uri=bolt,
                http_uri=None,
                image=str(row.get("Image") or ""),
                managed=False,
                container_id=str(row.get("ID") or "")[:12] or None,
                can_start=status != "running",
                detail="Docker Neo4j container (not in Control registry) — start/stop via Docker or import later",
            )
        )

    return views, notes
