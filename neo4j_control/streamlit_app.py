"""Streamlit UI for Neo4j Control (Phase 0–1).

Prefer launching via project-root ``app.py`` after ``pip install -e .``.
When this file is targeted directly, ensure the repo root is on ``sys.path``
so ``import neo4j_control`` works (Streamlit otherwise puts *this* directory first).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

try:
    from neo4j_control.audit import audit, read_audit_tail
    from neo4j_control.config import ensure_runtime_dirs, get_settings
    from neo4j_control.logging_setup import setup_logging
    from neo4j_control.services.aura import AuraClient
    from neo4j_control.services.desktop import (
        DesktopLifecycleError,
        desktop_start,
        desktop_stop,
        discover_desktop_dbms,
    )
    from neo4j_control.services.docker_discover import discover_docker_neo4j
    from neo4j_control.services.docker_neo4j import (
        DockerUnavailableError,
        LifecycleError,
        Neo4jDockerService,
        docker_available,
    )
    from neo4j_control.services.env_file import (
        ensure_env_file,
        get_env_value,
        mask_secret,
        upsert_env_values,
    )
    from neo4j_control.services.mcp import McpActivator
    from neo4j_control.services.registry import RegistryError
except ModuleNotFoundError as exc:
    if getattr(exc, "name", "") == "neo4j_control" or "neo4j_control" in str(exc):
        raise ModuleNotFoundError(
            "Package 'neo4j_control' is not importable.\n\n"
            "Your traceback shows system Frameworks Streamlit and/or an outdated tree.\n"
            "From the repo root, use the project venv (not /Library/Frameworks/...):\n\n"
            "  git pull\n"
            "  python3 -m venv .venv && source .venv/bin/activate\n"
            "  python -m pip install -e .\n"
            "  python -m streamlit run app.py --server.port 8517 --server.address 127.0.0.1\n\n"
            "Or: ./run_app.sh\n"
            "In PyCharm, set the interpreter to .venv and run module 'streamlit' with\n"
            "parameters: run app.py --server.port 8517 --server.address 127.0.0.1\n"
        ) from exc
    raise

settings = ensure_runtime_dirs(get_settings())
logger = setup_logging(settings)
svc = Neo4jDockerService(settings)
mcp = McpActivator()


def get_aura_client() -> AuraClient:
    """Build Aura client from current .env / process env (after Settings save)."""
    return AuraClient(
        client_id=get_env_value("AURA_CLIENT_ID"),
        client_secret=get_env_value("AURA_CLIENT_SECRET"),
    )

st.set_page_config(
    page_title="Neo4j Control",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.25rem; max-width: 1100px; }
      div[data-testid="stMetricValue"] { font-size: 1.35rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _docker_banner() -> None:
    ok, detail = docker_available()
    if ok:
        st.success(f"Docker Compose available — {detail}")
    else:
        st.warning(
            f"**Docker not available:** {detail}. "
            "You can still create/list/delete **definitions** (compose files + registry). "
            "Start/stop need Docker on this machine."
        )


def _refresh() -> None:
    st.session_state.pop("instances_cache", None)


def page_overview() -> None:
    st.title("Database overview")
    st.caption(
        "Sky (Aura) · Neo4j Desktop (lokalt) · Docker (Control + andre containere). "
        "Genindlæs for at opdatere status."
    )
    if st.button("Refresh all sources", type="primary"):
        audit("overview.refresh", result="ok")
        st.rerun()

    # ——— Aura (cloud) ———
    st.subheader("Aura (sky)")
    probe = get_aura_client().probe()
    if probe.ok:
        st.success(probe.message)
    elif probe.configured:
        st.error(probe.message)
    else:
        st.info(
            "Aura er ikke konfigureret endnu. Gå til **Settings** i menuen og "
            "indtast Client ID + Client Secret (skrives til lokal `.env`)."
        )
        st.markdown("[Åbn Aura Console → API keys](https://console.neo4j.io)")
    if probe.instances:
        rows = [
            {
                "name": i.get("name"),
                "status": i.get("status"),
                "connection": i.get("connection_url"),
                "region": i.get("region"),
                "id": i.get("id"),
            }
            for i in probe.instances
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    elif probe.configured and probe.ok:
        st.write("Ingen Aura-instanser på denne konto.")

    st.divider()

    # ——— Neo4j Desktop ———
    st.subheader("Neo4j Desktop (lokalt)")
    st.caption(
        "Status bruger nu pid + port (ikke bare “port 7687 åben”). "
        "Flere DBMS deler ofte 7687 — kun én kan køre. "
        "**Fuld styring** af Docker er under Docker lifecycle; Desktop start/stop "
        "virker kun hvis et `neo4j`-script findes (ellers brug Neo4j Desktop-appen)."
    )
    desktop, desk_notes = discover_desktop_dbms()
    for note in desk_notes:
        st.info(note)
    if not desktop and not desk_notes:
        st.info("Ingen Desktop DBMS fundet.")
    for dbms in desktop:
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 2, 2])
            with c1:
                st.markdown(f"**{dbms.name}**")
                st.caption(f"ID `{dbms.id}` · {dbms.version or 'version?'}")
                if dbms.status_detail:
                    st.caption(dbms.status_detail)
            with c2:
                st.write(f"Status: `{dbms.status}`")
                st.write(dbms.bolt_uri or "Bolt port ukendt")
                dbs = ", ".join(d.name for d in dbms.databases) or "(ingen databases endnu)"
                st.write(f"Databases: {dbs}")
            with c3:
                st.caption(dbms.path)
                if dbms.controllable:
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button(
                            "Start",
                            key=f"desk-start-{dbms.id}",
                            disabled=dbms.status == "running",
                        ):
                            try:
                                msg = desktop_start(dbms.id)
                                audit("desktop.start", instance=dbms.name, result="ok")
                                st.success(msg)
                                st.rerun()
                            except DesktopLifecycleError as exc:
                                audit(
                                    "desktop.start",
                                    instance=dbms.name,
                                    result="error",
                                    detail={"error": str(exc)[:500]},
                                )
                                st.error(str(exc))
                    with b2:
                        if st.button(
                            "Stop",
                            key=f"desk-stop-{dbms.id}",
                            disabled=dbms.status == "stopped",
                        ):
                            try:
                                msg = desktop_stop(dbms.id)
                                audit("desktop.stop", instance=dbms.name, result="ok")
                                st.success(msg)
                                st.rerun()
                            except DesktopLifecycleError as exc:
                                st.error(str(exc))
                else:
                    st.caption("Start/stop: brug Neo4j Desktop (ingen neo4j-bin fundet).")

    st.divider()

    # ——— Docker ———
    st.subheader("Docker")
    docker_views, docker_notes = discover_docker_neo4j(svc)
    for note in docker_notes:
        st.warning(note)
    running = [v for v in docker_views if v.status == "running"]
    startable = [v for v in docker_views if v.can_start and v.managed]
    m1, m2, m3 = st.columns(3)
    m1.metric("Docker Neo4j (alle)", len(docker_views))
    m2.metric("Kørende nu", len(running))
    m3.metric("Kan startes (Control)", len(startable))

    if not docker_views:
        st.info("Ingen Docker Neo4j endnu. Opret under **Docker lifecycle**.")
    for v in docker_views:
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 2, 2])
            with c1:
                badge = "Control" if v.managed else "andet Docker"
                st.markdown(f"**{v.name}** · _{badge}_")
                st.caption(v.detail)
            with c2:
                st.write(f"Status: `{v.status}`")
                st.write(v.bolt_uri or "—")
                if v.image:
                    st.caption(v.image)
            with c3:
                if v.managed and v.can_start:
                    if st.button("Start", key=f"ov-start-{v.name}"):
                        try:
                            with st.spinner(f"Starter {v.name}…"):
                                svc.start(v.name)
                            st.success(f"Startet {v.name}")
                            st.rerun()
                        except (DockerUnavailableError, LifecycleError, RegistryError) as exc:
                            st.error(str(exc))
                elif v.managed and v.status == "running":
                    if st.button("Stop", key=f"ov-stop-{v.name}"):
                        try:
                            svc.stop(v.name)
                            st.rerun()
                        except (DockerUnavailableError, LifecycleError, RegistryError) as exc:
                            st.error(str(exc))
                elif not v.managed:
                    st.caption("Ikke styret af Control — brug Docker Desktop/CLI.")


def page_instances() -> None:
    st.title("Docker lifecycle")
    st.caption("Create / start / stop / delete Compose stacks. See Overview for Desktop + Aura.")
    _docker_banner()

    col_a, col_b = st.columns([2, 1])
    with col_a:
        if st.button("Refresh list", type="secondary"):
            _refresh()
            try:
                instances = svc.list_instances()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
                instances = svc.registry.list()
        else:
            try:
                instances = svc.list_instances()
            except Exception:  # noqa: BLE001
                instances = svc.registry.list()
    with col_b:
        st.metric("Local instances", len(instances))

    if not instances:
        st.info("No local instances yet. Create one below.")
    else:
        for inst in instances:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 2])
                with c1:
                    st.subheader(inst.name)
                    st.write(f"Status: `{inst.status}`")
                    if inst.last_error:
                        st.caption(f"Last error: {inst.last_error}")
                with c2:
                    st.write(f"Bolt: `{inst.bolt_uri}`")
                    st.write(f"HTTP: `{inst.http_uri}`")
                    st.caption(f"Image: `{inst.image}`")
                with c3:
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button("Start", key=f"start-{inst.name}", use_container_width=True):
                            try:
                                with st.spinner(f"Starting {inst.name}…"):
                                    svc.start(inst.name)
                                st.success(f"Started {inst.name}")
                                st.rerun()
                            except (DockerUnavailableError, LifecycleError, RegistryError) as exc:
                                st.error(str(exc))
                    with b2:
                        if st.button("Stop", key=f"stop-{inst.name}", use_container_width=True):
                            try:
                                with st.spinner(f"Stopping {inst.name}…"):
                                    svc.stop(inst.name)
                                st.success(f"Stopped {inst.name}")
                                st.rerun()
                            except (DockerUnavailableError, LifecycleError, RegistryError) as exc:
                                st.error(str(exc))
                    with b3:
                        st.write("")  # spacer for alignment

                with st.expander(f"Delete `{inst.name}` (typed confirm)", expanded=False):
                    st.error(
                        "This removes the Compose stack, volumes (by default), and registry entry. "
                        "Type the instance name to confirm."
                    )
                    confirm = st.text_input(
                        "Type instance name to delete",
                        key=f"del-confirm-{inst.name}",
                        placeholder=inst.name,
                    )
                    remove_vols = st.checkbox(
                        "Also remove Docker volumes (data)",
                        value=True,
                        key=f"del-vols-{inst.name}",
                    )
                    if st.button(
                        "Delete permanently",
                        key=f"del-btn-{inst.name}",
                        type="primary",
                        disabled=confirm.strip() != inst.name,
                    ):
                        try:
                            svc.delete(
                                inst.name,
                                confirm_name=confirm,
                                remove_volumes=remove_vols,
                            )
                            st.success(f"Deleted {inst.name}")
                            st.rerun()
                        except (LifecycleError, RegistryError, DockerUnavailableError) as exc:
                            st.error(str(exc))

    st.divider()
    st.subheader("Create local instance")
    with st.form("create_form", clear_on_submit=True):
        name = st.text_input("Name", placeholder="demo-local", help="lowercase, hyphens ok")
        password = st.text_input(
            "Neo4j password",
            type="password",
            value=settings.default_password,
            help="Stored only in the stack's .env (gitignored).",
        )
        start_now = st.checkbox("Start after create", value=False)
        submitted = st.form_submit_button("Create", type="primary")
        if submitted:
            try:
                with st.spinner("Creating…"):
                    inst = svc.create(name, password=password or None, start=start_now)
                st.success(
                    f"Created **{inst.name}** · Bolt `{inst.bolt_uri}` · status `{inst.status}`"
                )
                st.rerun()
            except (LifecycleError, RegistryError, DockerUnavailableError) as exc:
                st.error(str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.exception("create failed")
                st.error(str(exc))


def page_settings() -> None:
    st.title("Settings")
    st.caption(
        "Gem Aura API-nøgler i lokal `.env` (gitignored). "
        "Hent nøgler i [Aura Console → Account → API keys](https://console.neo4j.io)."
    )
    env_file = ensure_env_file()
    current_id = get_env_value("AURA_CLIENT_ID")
    current_secret = get_env_value("AURA_CLIENT_SECRET")

    st.subheader("Aura credentials")
    st.write(
        f"Status: **{'konfigureret' if current_id and current_secret else 'ikke sat'}** · "
        f"fil: `{env_file}`"
    )
    if current_id:
        st.caption(f"Client ID nu: `{mask_secret(current_id, keep=6)}`")
    if current_secret:
        st.caption(f"Client Secret nu: `{mask_secret(current_secret, keep=4)}`")

    with st.form("aura_settings_form"):
        client_id = st.text_input(
            "AURA_CLIENT_ID",
            value=current_id,
            help="Client ID fra Aura API credentials",
        )
        client_secret = st.text_input(
            "AURA_CLIENT_SECRET",
            value="",
            type="password",
            help="Lad være tom for at beholde den eksisterende secret; skriv ny for at erstatte.",
            placeholder="(uændret hvis tom)" if current_secret else "indsæt secret",
        )
        clear = st.checkbox("Fjern Aura-credentials fra .env", value=False)
        submitted = st.form_submit_button("Gem i .env", type="primary")
        if submitted:
            try:
                if clear:
                    upsert_env_values({"AURA_CLIENT_ID": "", "AURA_CLIENT_SECRET": ""})
                    audit("settings.aura.clear", result="ok")
                    st.success("Aura-credentials fjernet fra .env")
                else:
                    updates: dict[str, str] = {}
                    if client_id.strip():
                        updates["AURA_CLIENT_ID"] = client_id.strip()
                    elif not current_id:
                        st.error("Client ID mangler.")
                        st.stop()
                    if client_secret.strip():
                        updates["AURA_CLIENT_SECRET"] = client_secret.strip()
                    elif not current_secret:
                        st.error("Client Secret mangler (første gang skal den udfyldes).")
                        st.stop()
                    if not updates:
                        st.info("Ingen ændringer.")
                    else:
                        upsert_env_values(updates)
                        audit(
                            "settings.aura.save",
                            result="ok",
                            detail={"keys": list(updates.keys())},
                        )
                        st.success("Gemt i .env — Overview kan nu liste Aura-instanser.")
                st.rerun()
            except OSError as exc:
                st.error(f"Kunne ikke skrive .env: {exc}")

    st.divider()
    if st.button("Test Aura-forbindelse"):
        probe = get_aura_client().probe()
        audit(
            "settings.aura.probe",
            result="ok" if probe.ok else "error",
            detail={"configured": probe.configured, "count": len(probe.instances)},
        )
        if probe.ok:
            st.success(probe.message)
            if probe.instances:
                st.dataframe(
                    [
                        {
                            "name": i.get("name"),
                            "status": i.get("status"),
                            "connection": i.get("connection_url"),
                        }
                        for i in probe.instances
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
        elif probe.configured:
            st.error(probe.message)
        else:
            st.warning(probe.message)


def page_aura() -> None:
    st.title("Aura sync")
    st.caption("List via Overview/Settings. Sync/move kommer senere.")
    probe = get_aura_client().probe()
    if not probe.configured:
        st.info("Ingen credentials — indtast dem under **Settings**.")
    elif probe.ok:
        st.success(probe.message)
    else:
        st.warning(probe.message)
    st.write("Planned actions:")
    st.markdown(
        """
        - Connect with Aura API credentials (Settings → `.env`)
        - List Aura instances (Overview)
        - Directional sync / move with dry-run + verify
        - Aura remains source of truth until sync verified
        """
    )
    if st.button("Probe Aura"):
        probe = get_aura_client().probe()
        audit(
            "aura.probe",
            result="ok" if probe.ok else "error",
            detail={"configured": probe.configured, "count": len(probe.instances)},
        )
        # Never dump secrets; strip raw blobs
        safe = [
            {k: v for k, v in i.items() if k != "raw"} for i in probe.instances
        ]
        st.json(
            {
                "configured": probe.configured,
                "ok": probe.ok,
                "message": probe.message,
                "instances": safe,
            }
        )


def page_mcp() -> None:
    st.title("MCP activate")
    st.caption("Phase 4 placeholder — MCP runs on the host, outside Docker.")
    instances = svc.registry.list()
    names = [i.name for i in instances]
    choice = st.selectbox("Target local instance", options=["—"] + names)
    bolt = None
    if choice != "—":
        inst = svc.registry.get(choice)
        bolt = inst.bolt_uri if inst else None
        st.code(bolt or "", language=None)

    status = mcp.status(bolt)
    st.write(status.message)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Activate MCP (stub)", disabled=not bolt, type="primary"):
            result = mcp.activate(bolt or "")
            audit("mcp.activate", instance=choice if choice != "—" else None, result="stub")
            st.info(result.message)
    with c2:
        if st.button("Deactivate MCP (stub)"):
            result = mcp.deactivate()
            audit("mcp.deactivate", result="stub")
            st.info(result.message)


def page_logs() -> None:
    st.title("Logs & audit")
    tab1, tab2 = st.tabs(["Audit trail", "App log"])
    with tab1:
        events = read_audit_tail(80, settings)
        if not events:
            st.info(f"No audit events yet. File: `{settings.audit_log_path}`")
        else:
            st.dataframe(events, use_container_width=True, hide_index=True)
    with tab2:
        path = settings.app_log_path
        if path.exists():
            text = path.read_text(encoding="utf-8")
            st.code(text[-12000:] if len(text) > 12000 else text, language="log")
        else:
            st.info(f"No app log yet at `{path}`")


def main() -> None:
    with st.sidebar:
        st.markdown("### Neo4j Control")
        page = st.radio(
            "Navigate",
            [
                "Overview",
                "Docker lifecycle",
                "Aura sync",
                "Settings",
                "MCP activate",
                "Logs & audit",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        st.caption(f"Image pin: `{settings.neo4j_image}`")
        st.caption(f"Data: `{settings.data_dir}`")
        aura_ok = bool(get_env_value("AURA_CLIENT_ID") and get_env_value("AURA_CLIENT_SECRET"))
        st.caption(f"Aura: {'sat' if aura_ok else 'ikke sat'} (Settings)")

    if page == "Overview":
        page_overview()
    elif page == "Docker lifecycle":
        page_instances()
    elif page == "Aura sync":
        page_aura()
    elif page == "Settings":
        page_settings()
    elif page == "MCP activate":
        page_mcp()
    else:
        page_logs()


if __name__ == "__main__":
    main()
