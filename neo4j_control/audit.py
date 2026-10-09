"""Append-only audit trail (JSON Lines) at logs/audit.log."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j_control.config import Settings, ensure_runtime_dirs

_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit(
    action: str,
    *,
    instance: str | None = None,
    result: str = "ok",
    detail: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> None:
    """Append one audit event. Never raises to callers (best-effort)."""
    settings = ensure_runtime_dirs(settings)
    path: Path = settings.audit_log_path
    event = {
        "ts": _now_iso(),
        "action": action,
        "instance": instance,
        "result": result,
        "detail": detail or {},
    }
    line = json.dumps(event, ensure_ascii=False) + "\n"
    try:
        with _lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
    except OSError:
        # Avoid breaking the UI if the log disk is unavailable
        pass


def read_audit_tail(n: int = 50, settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = ensure_runtime_dirs(settings)
    path = settings.audit_log_path
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(events))
