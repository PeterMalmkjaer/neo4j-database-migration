"""Persistent registry of local Neo4j instance definitions."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Iterable

from neo4j_control.config import Settings, ensure_runtime_dirs
from neo4j_control.models import Neo4jInstance

_lock = threading.Lock()
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,47}$")


class RegistryError(ValueError):
    pass


def validate_name(name: str) -> str:
    name = name.strip().lower()
    if not _NAME_RE.match(name):
        raise RegistryError(
            "Name must be 2–48 chars: start with a letter, then lowercase letters, "
            "digits, or hyphens (e.g. demo-local)."
        )
    return name


class InstanceRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = ensure_runtime_dirs(settings)
        self.path: Path = self.settings.registry_path

    def _read(self) -> dict[str, Neo4jInstance]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        items = raw.get("instances", raw if isinstance(raw, list) else [])
        out: dict[str, Neo4jInstance] = {}
        for item in items:
            inst = Neo4jInstance.from_dict(item)
            out[inst.name] = inst
        return out

    def _write(self, instances: dict[str, Neo4jInstance]) -> None:
        payload = {
            "version": 1,
            "instances": [i.to_dict() for i in sorted(instances.values(), key=lambda x: x.name)],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> list[Neo4jInstance]:
        with _lock:
            return list(self._read().values())

    def get(self, name: str) -> Neo4jInstance | None:
        with _lock:
            return self._read().get(name)

    def add(self, instance: Neo4jInstance) -> Neo4jInstance:
        name = validate_name(instance.name)
        instance.name = name
        with _lock:
            current = self._read()
            if name in current:
                raise RegistryError(f"Instance already exists: {name}")
            current[name] = instance
            self._write(current)
        return instance

    def update(self, instance: Neo4jInstance) -> Neo4jInstance:
        with _lock:
            current = self._read()
            if instance.name not in current:
                raise RegistryError(f"Unknown instance: {instance.name}")
            current[instance.name] = instance
            self._write(current)
        return instance

    def remove(self, name: str) -> None:
        with _lock:
            current = self._read()
            if name not in current:
                raise RegistryError(f"Unknown instance: {name}")
            del current[name]
            self._write(current)

    def used_ports(self) -> set[int]:
        with _lock:
            ports: set[int] = set()
            for inst in self._read().values():
                ports.add(inst.bolt_port)
                ports.add(inst.http_port)
            return ports

    def allocate_ports(self) -> tuple[int, int]:
        used = self.used_ports()
        bolt = self.settings.bolt_port_base
        http = self.settings.http_port_base
        # Keep HTTP = bolt - 213 typical pairing (7687/7474); step by 10
        while bolt in used or http in used:
            bolt += 10
            http += 10
        return bolt, http

    def names(self) -> Iterable[str]:
        return [i.name for i in self.list()]
