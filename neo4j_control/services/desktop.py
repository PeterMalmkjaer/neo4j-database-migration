"""Discover Neo4j Desktop local DBMS instances (macOS / Linux / Windows)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from neo4j_control.services.bolt import tcp_open

# Skip Neo4j internal DB folders when listing logical databases
_SKIP_DB_NAMES = frozenset(
    {
        "system",
        "system_schema",
        "store_lock",
        "temp",
    }
)


@dataclass
class DesktopDatabase:
    name: str
    path: str


@dataclass
class DesktopDbms:
    id: str
    name: str
    version: str | None
    bolt_port: int | None
    bolt_uri: str | None
    path: str
    status: str  # running | stopped | unknown
    databases: list[DesktopDatabase] = field(default_factory=list)
    source: str = "neo4j-desktop"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def desktop_candidate_roots() -> list[Path]:
    """Known Neo4j Desktop data roots across OSes (+ optional override)."""
    home = Path.home()
    env = os.getenv("NEO4J_DESKTOP_DATA_DIR")
    roots: list[Path] = []
    if env:
        roots.append(Path(env).expanduser())
    roots.extend(
        [
            home
            / "Library/Application Support/neo4j-desktop/Application/Data/dbmss",
            home
            / "Library/Application Support/neo4j-desktop/Application/relate-data/dbmss",
            home / ".config/Neo4j Desktop/Application/Data/dbmss",
            home / ".config/Neo4j Desktop/Application/relate-data/dbmss",
            home / "AppData/Roaming/Neo4j Desktop/Application/Data/dbmss",
            home / "AppData/Local/Neo4j Desktop/Application/Data/dbmss",
        ]
    )
    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _read_bolt_port(conf: Path) -> int | None:
    if not conf.exists():
        return None
    try:
        text = conf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    patterns = [
        r"server\.bolt\.listen_address\s*=\s*:?(\d+)",
        r"server\.bolt\.advertised_address\s*=\s*[^:\s]+:(\d+)",
        r"dbms\.connector\.bolt\.listen_address\s*=\s*:?(\d+)",
        r"dbms\.connector\.bolt\.advertised_address\s*=\s*[^:\s]+:(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return 7687  # Desktop default when conf present but unparsed


def _list_databases(dbms_dir: Path) -> list[DesktopDatabase]:
    candidates = [
        dbms_dir / "data" / "databases",
        dbms_dir / "databases",
    ]
    found: list[DesktopDatabase] = []
    for base in candidates:
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            name = child.name
            if name.startswith(".") or name in _SKIP_DB_NAMES:
                continue
            if name.endswith("_transaction") or name.endswith(".lock"):
                continue
            found.append(DesktopDatabase(name=name, path=str(child)))
        if found:
            break
    return found


def _name_from_meta(dbms_dir: Path, fallback_id: str) -> tuple[str, str | None]:
    """Try Desktop JSON metadata for display name + version."""
    version = None
    name = fallback_id
    meta_files = [
        dbms_dir / ".installation",
        dbms_dir / "installation.json",
        dbms_dir / "meta.json",
        dbms_dir.parent.parent / "relate-data" / "dbmss" / f"{dbms_dir.name}.json",
    ]
    # Also scan sibling relate projects for this id
    for meta in meta_files:
        if not meta.exists() or not meta.is_file():
            continue
        try:
            raw = meta.read_text(encoding="utf-8", errors="ignore").strip()
            if not raw.startswith("{"):
                continue
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue
        name = (
            data.get("name")
            or data.get("dbms", {}).get("name")
            or data.get("installation", {}).get("name")
            or name
        )
        version = (
            data.get("version")
            or data.get("dbms", {}).get("version")
            or data.get("installation", {}).get("version")
            or version
        )
    # Desktop sometimes stores names in relate-data/projects/*/dbmss.json — best-effort
    relate = Path.home() / "Library/Application Support/neo4j-desktop/Application/relate-data"
    if relate.is_dir():
        for path in relate.rglob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, json.JSONDecodeError):
                continue
            blob = json.dumps(data)
            if fallback_id not in blob and dbms_dir.name not in blob:
                continue
            # Walk nested dicts/lists for matching id + name
            stack: list[Any] = [data]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    cid = str(cur.get("id") or cur.get("dbmsId") or "")
                    if fallback_id in cid or dbms_dir.name in cid or cid == fallback_id:
                        if cur.get("name"):
                            name = str(cur["name"])
                        if cur.get("version"):
                            version = str(cur["version"])
                    stack.extend(cur.values())
                elif isinstance(cur, list):
                    stack.extend(cur)
    return name, version


def discover_desktop_dbms() -> tuple[list[DesktopDbms], list[str]]:
    """Return (instances, notes). Notes explain missing roots / scan limits."""
    notes: list[str] = []
    results: list[DesktopDbms] = []
    seen_ids: set[str] = set()

    any_root = False
    for root in desktop_candidate_roots():
        if not root.is_dir():
            continue
        any_root = True
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            folder = child.name
            if not (folder.startswith("dbms-") or len(folder) >= 8):
                # Prefer dbms-* but accept UUID-looking dirs under dbmss/
                if root.name != "dbmss":
                    continue
            dbms_id = folder.removeprefix("dbms-")
            if dbms_id in seen_ids:
                continue
            conf = child / "conf" / "neo4j.conf"
            if not conf.exists():
                conf = child / "neo4j.conf"
            # Skip empty / non-dbms folders
            if not conf.exists() and not (child / "data").exists():
                continue
            seen_ids.add(dbms_id)
            bolt = _read_bolt_port(conf) if conf.exists() else None
            name, version = _name_from_meta(child, dbms_id)
            status = "unknown"
            bolt_uri = None
            if bolt:
                bolt_uri = f"neo4j://127.0.0.1:{bolt}"
                status = "running" if tcp_open("127.0.0.1", bolt) else "stopped"
            results.append(
                DesktopDbms(
                    id=dbms_id,
                    name=name,
                    version=version,
                    bolt_port=bolt,
                    bolt_uri=bolt_uri,
                    path=str(child),
                    status=status,
                    databases=_list_databases(child),
                )
            )

    if not any_root:
        notes.append(
            "No Neo4j Desktop data folder found. On this Mac, expected under "
            "~/Library/Application Support/neo4j-desktop/Application/Data/dbmss — "
            "or set NEO4J_DESKTOP_DATA_DIR in .env."
        )
    elif not results:
        notes.append("Desktop data folder exists but no DBMS directories with conf/data were found.")
    return results, notes
