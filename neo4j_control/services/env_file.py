"""Read/update project ``.env`` without committing secrets."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

from neo4j_control.config import PROJECT_ROOT

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def env_path() -> Path:
    return PROJECT_ROOT / ".env"


def ensure_env_file() -> Path:
    path = env_path()
    if not path.exists():
        example = PROJECT_ROOT / ".env.example"
        if example.exists():
            path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            path.write_text("# Neo4j Control local secrets — do not commit\n", encoding="utf-8")
    return path


def read_env_map(path: Path | None = None) -> dict[str, str]:
    path = path or ensure_env_file()
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _ENV_LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        out[key] = val
    return out


def get_env_value(key: str, default: str = "") -> str:
    """Prefer process env, then .env file."""
    if key in os.environ and os.environ[key] != "":
        return os.environ[key]
    return read_env_map().get(key, default)


def upsert_env_values(updates: dict[str, str], *, path: Path | None = None) -> Path:
    """
    Set or replace keys in ``.env``. Empty string removes the assignment
    (writes a commented placeholder) so secrets can be cleared.
    Reloads into ``os.environ`` for the current process.
    """
    path = ensure_env_file() if path is None else path
    if not path.exists():
        path.write_text("", encoding="utf-8")

    lines = path.read_text(encoding="utf-8").splitlines()
    remaining = dict(updates)
    new_lines: list[str] = []
    seen: set[str] = set()

    for raw in lines:
        m = _ENV_LINE.match(raw.strip()) if raw.strip() and not raw.strip().startswith("#") else None
        if not m:
            new_lines.append(raw)
            continue
        key = m.group(1)
        if key in remaining:
            val = remaining.pop(key)
            seen.add(key)
            if val == "":
                new_lines.append(f"# {key}=")
            else:
                new_lines.append(f"{key}={_format_value(val)}")
            # keep process env in sync
            if val == "":
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        else:
            new_lines.append(raw)

    for key, val in remaining.items():
        if val == "":
            new_lines.append(f"# {key}=")
            os.environ.pop(key, None)
        else:
            new_lines.append(f"{key}={_format_value(val)}")
            os.environ[key] = val

    text = "\n".join(new_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    load_dotenv(path, override=True)
    return path


def _format_value(val: str) -> str:
    if any(c in val for c in ' \t#"\''):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return val


def mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return "(tom)"
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "…" + ("*" * min(8, len(value) - keep))
