"""Discover (and optionally start/stop) Neo4j Desktop local DBMS instances."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from neo4j_control.logging_setup import get_logger
from neo4j_control.services.bolt import tcp_open

log = get_logger("neo4j_control.desktop")

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
    status: str  # running | stopped | unknown | port-busy
    databases: list[DesktopDatabase] = field(default_factory=list)
    source: str = "neo4j-desktop"
    status_detail: str = ""
    controllable: bool = False  # True if we found a neo4j start/stop script
    neo4j_bin: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DesktopLifecycleError(RuntimeError):
    pass


def desktop_candidate_roots() -> list[Path]:
    home = Path.home()
    env = os.getenv("NEO4J_DESKTOP_DATA_DIR")
    roots: list[Path] = []
    if env:
        roots.append(Path(env).expanduser())
    roots.extend(
        [
            home / "Library/Application Support/neo4j-desktop/Application/Data/dbmss",
            home / "Library/Application Support/neo4j-desktop/Application/relate-data/dbmss",
            home / ".config/Neo4j Desktop/Application/Data/dbmss",
            home / ".config/Neo4j Desktop/Application/relate-data/dbmss",
            home / "AppData/Roaming/Neo4j Desktop/Application/Data/dbmss",
            home / "AppData/Local/Neo4j Desktop/Application/Data/dbmss",
        ]
    )
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _read_bolt_port(conf: Path) -> int | None:
    """Parse Bolt listen port from neo4j.conf. No silent default (avoids false 'running')."""
    if not conf.exists():
        return None
    try:
        text = conf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    patterns = [
        r"server\.bolt\.listen_address\s*=\s*(?:\[[^\]]*\]|[^:\s#]*):(\d+)",
        r"server\.bolt\.listen_address\s*=\s*:(\d+)",
        r"server\.bolt\.advertised_address\s*=\s*[^:\s#]+:(\d+)",
        r"dbms\.connector\.bolt\.listen_address\s*=\s*:?(\d+)",
        r"dbms\.connector\.bolt\.advertised_address\s*=\s*[^:\s#]+:(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:  # noqa: BLE001
        return False


def _read_pid_file(dbms_dir: Path) -> int | None:
    candidates = [
        dbms_dir / "run" / "neo4j.pid",
        dbms_dir / "data" / "neo4j.pid",
        dbms_dir / "neo4j.pid",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            pid = int(text.split()[0])
            if pid > 0:
                return pid
        except (OSError, ValueError, IndexError):
            continue
    return None


def _store_lock_held(dbms_dir: Path) -> bool:
    """Best-effort: Neo4j holds store_lock while the DBMS is up."""
    lock = dbms_dir / "data" / "databases" / "store_lock"
    if not lock.exists():
        return False
    # Presence alone is not enough on all versions; combine with pid/port.
    try:
        return lock.stat().st_size >= 0 and lock.is_file()
    except OSError:
        return False


def _infer_status(dbms_dir: Path, bolt: int | None) -> tuple[str, str]:
    """
    Infer running/stopped carefully.

    Never mark running solely because *some* process listens on a shared default
    port when several Desktop DBMS configs point at the same port.
    """
    pid = _read_pid_file(dbms_dir)
    if pid is not None:
        if _pid_running(pid):
            return "running", f"neo4j.pid={pid} (process alive)"
        return "stopped", f"stale neo4j.pid={pid} (process not alive)"

    if bolt is None:
        return "unknown", "Bolt-port ikke fundet i neo4j.conf"

    port_open = tcp_open("127.0.0.1", bolt, timeout=0.4)
    if not port_open:
        return "stopped", f"Intet lytter på 127.0.0.1:{bolt}"

    # Port open but no pid for *this* DBMS → ambiguous (shared port / other process)
    return (
        "port-busy",
        f"Port {bolt} er åben, men ingen neo4j.pid for denne DBMS — "
        "kan være en anden DBMS/Docker på samme port (typisk 7687).",
    )


def _resolve_shared_ports(results: list[DesktopDbms]) -> None:
    """If several DBMS share a port, only a pid-backed one may stay 'running'."""
    by_port: dict[int, list[DesktopDbms]] = {}
    for item in results:
        if item.bolt_port:
            by_port.setdefault(item.bolt_port, []).append(item)
    for port, group in by_port.items():
        if len(group) < 2:
            continue
        runningish = [g for g in group if g.status in {"running", "port-busy"}]
        if not runningish:
            continue
        pid_backed = [g for g in runningish if g.status == "running"]
        if pid_backed:
            winner = pid_backed[0]
            for g in group:
                if g is winner:
                    continue
                if g.status in {"running", "port-busy"}:
                    g.status = "stopped"
                    g.status_detail = (
                        f"Deler port {port} med '{winner.name}' — markeret stopped "
                        "(kun én DBMS kan lytte ad gangen)."
                    )
        else:
            # Port open, no pid: mark all as port-busy / stopped clarification
            for g in group:
                if g.status == "port-busy":
                    g.status_detail = (
                        f"Flere Desktop-DBMS er konfigureret til port {port}; "
                        f"porten er åben, men det er uklart hvilken (brug Neo4j Desktop)."
                    )


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


def _find_neo4j_bin(dbms_dir: Path) -> Path | None:
    """Locate neo4j start script for this DBMS (Desktop layout varies)."""
    direct = [
        dbms_dir / "bin" / "neo4j",
        dbms_dir / "bin" / "neo4j.bat",
    ]
    for p in direct:
        if p.is_file():
            return p
    # Desktop shared distributions next to Data/
    # .../Application/Data/dbmss/dbms-x  → .../Application/Data/offline/neo4j-enterprise-...
    data_root = dbms_dir.parent.parent  # Data/
    for pattern in ("offline", "distributions", "apps"):
        base = data_root / pattern
        if not base.is_dir():
            continue
        for cand in base.rglob("neo4j"):
            if cand.is_file() and cand.parent.name == "bin":
                return cand
    app = Path.home() / "Library/Application Support/neo4j-desktop/Application"
    for cand in app.rglob("neo4j"):
        if cand.is_file() and cand.parent.name == "bin" and "neo4j" in str(cand).lower():
            # Prefer version-ish paths; first hit is ok as last resort
            return cand
    return None


def _name_from_meta(dbms_dir: Path, fallback_id: str) -> tuple[str, str | None]:
    version = None
    name = fallback_id
    meta_files = [
        dbms_dir / ".installation",
        dbms_dir / "installation.json",
        dbms_dir / "meta.json",
    ]
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
            if not folder.startswith("dbms-") and root.name == "dbmss":
                # UUID-style dirs under dbmss/
                if len(folder) < 8:
                    continue
            elif not folder.startswith("dbms-"):
                continue
            dbms_id = folder.removeprefix("dbms-")
            if dbms_id in seen_ids:
                continue
            conf = child / "conf" / "neo4j.conf"
            if not conf.exists():
                conf = child / "neo4j.conf"
            if not conf.exists() and not (child / "data").exists():
                continue
            seen_ids.add(dbms_id)
            bolt = _read_bolt_port(conf) if conf.exists() else None
            name, version = _name_from_meta(child, dbms_id)
            status, detail = _infer_status(child, bolt)
            neo4j_bin = _find_neo4j_bin(child)
            results.append(
                DesktopDbms(
                    id=dbms_id,
                    name=name,
                    version=version,
                    bolt_port=bolt,
                    bolt_uri=f"neo4j://127.0.0.1:{bolt}" if bolt else None,
                    path=str(child),
                    status=status,
                    databases=_list_databases(child),
                    status_detail=detail,
                    controllable=neo4j_bin is not None,
                    neo4j_bin=str(neo4j_bin) if neo4j_bin else None,
                )
            )

    _resolve_shared_ports(results)

    if not any_root:
        notes.append(
            "Ingen Neo4j Desktop-datamappe fundet. Forventet på Mac: "
            "~/Library/Application Support/neo4j-desktop/Application/Data/dbmss — "
            "eller sæt NEO4J_DESKTOP_DATA_DIR i .env."
        )
    elif not results:
        notes.append("Desktop-mappe findes, men ingen DBMS med conf/data.")
    else:
        shared = {}
        for r in results:
            if r.bolt_port:
                shared.setdefault(r.bolt_port, 0)
                shared[r.bolt_port] += 1
        clashes = [p for p, n in shared.items() if n > 1]
        if clashes:
            notes.append(
                "Flere Desktop-DBMS deler Bolt-port "
                + ", ".join(str(p) for p in clashes)
                + " — kun én kan køre ad gangen; status bruger nu pid/port-forsigtighed."
            )
        notes.append(
            "Desktop start/stop fra appen er begrænset (kræver neo4j-bin). "
            "Sikker styring af Docker sker under Docker lifecycle. "
            "Aura/Desktop synk kommer senere."
        )
    return results, notes


def desktop_start(dbms_id: str) -> str:
    items, _ = discover_desktop_dbms()
    match = next((i for i in items if i.id == dbms_id or i.name == dbms_id), None)
    if not match:
        raise DesktopLifecycleError(f"Ukendt Desktop DBMS: {dbms_id}")
    if not match.neo4j_bin:
        raise DesktopLifecycleError(
            "Ingen neo4j start-script fundet for denne Desktop-DBMS. "
            "Start den i Neo4j Desktop, eller opret en Docker-stack under Docker lifecycle."
        )
    if match.status == "running":
        return f"{match.name} kører allerede"
    # Warn on shared port already busy
    if match.bolt_port and tcp_open("127.0.0.1", match.bolt_port, timeout=0.3):
        raise DesktopLifecycleError(
            f"Port {match.bolt_port} er allerede i brug. Stop den anden DBMS først."
        )
    env = os.environ.copy()
    # Point NEO4J_HOME at dbms dir when using a shared binary
    env.setdefault("NEO4J_HOME", match.path)
    proc = subprocess.run(
        [match.neo4j_bin, "start"],
        cwd=match.path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    log.info("desktop start %s rc=%s", match.name, proc.returncode)
    if proc.returncode != 0:
        raise DesktopLifecycleError(
            (proc.stderr or proc.stdout or "neo4j start failed").strip()[:2000]
        )
    return (proc.stdout or f"Startet {match.name}").strip()


def desktop_stop(dbms_id: str) -> str:
    items, _ = discover_desktop_dbms()
    match = next((i for i in items if i.id == dbms_id or i.name == dbms_id), None)
    if not match:
        raise DesktopLifecycleError(f"Ukendt Desktop DBMS: {dbms_id}")
    if not match.neo4j_bin:
        raise DesktopLifecycleError(
            "Ingen neo4j stop-script fundet. Stop i Neo4j Desktop i stedet."
        )
    env = os.environ.copy()
    env.setdefault("NEO4J_HOME", match.path)
    proc = subprocess.run(
        [match.neo4j_bin, "stop"],
        cwd=match.path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    log.info("desktop stop %s rc=%s", match.name, proc.returncode)
    if proc.returncode != 0:
        raise DesktopLifecycleError(
            (proc.stderr or proc.stdout or "neo4j stop failed").strip()[:2000]
        )
    return (proc.stdout or f"Stoppet {match.name}").strip()
