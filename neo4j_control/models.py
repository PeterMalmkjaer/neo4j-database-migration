"""Domain models for local Neo4j instances."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

InstanceStatus = Literal[
    "defined",
    "starting",
    "running",
    "stopped",
    "error",
    "unknown",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Neo4jInstance:
    name: str
    bolt_port: int
    http_port: int
    compose_dir: str
    image: str
    created_at: str = field(default_factory=_now_iso)
    status: InstanceStatus = "defined"
    last_error: str | None = None
    password_env: str = "NEO4J_AUTH"  # password lives in compose/.env, not registry

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Neo4jInstance:
        return cls(
            name=data["name"],
            bolt_port=int(data["bolt_port"]),
            http_port=int(data["http_port"]),
            compose_dir=data["compose_dir"],
            image=data["image"],
            created_at=data.get("created_at", _now_iso()),
            status=data.get("status", "defined"),
            last_error=data.get("last_error"),
            password_env=data.get("password_env", "NEO4J_AUTH"),
        )

    @property
    def bolt_uri(self) -> str:
        return f"bolt://127.0.0.1:{self.bolt_port}"

    @property
    def http_uri(self) -> str:
        return f"http://127.0.0.1:{self.http_port}"
