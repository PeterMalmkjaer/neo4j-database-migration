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

from neo4j_control.audit import audit, read_audit_tail
from neo4j_control.config import ensure_runtime_dirs, get_settings
from neo4j_control.logging_setup import setup_logging
from neo4j_control.services.aura import AuraClient
from neo4j_control.services.docker_neo4j import (
    DockerUnavailableError,
    LifecycleError,
    Neo4jDockerService,
    docker_available,
)
from neo4j_control.services.mcp import McpActivator
from neo4j_control.services.registry import RegistryError

settings = ensure_runtime_dirs(get_settings())
logger = setup_logging(settings)
svc = Neo4jDockerService(settings)
aura = AuraClient(
    client_id=os.getenv("AURA_CLIENT_ID"),
    client_secret=os.getenv("AURA_CLIENT_SECRET"),
)
mcp = McpActivator()

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


def page_instances() -> None:
    st.title("Neo4j Control")
    st.caption("Local Docker Neo4j lifecycle · Aura sync & MCP activate later")
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


def page_aura() -> None:
    st.title("Aura sync")
    st.caption("Phase 2 placeholder — no live credentials required for Phase 0–1.")
    probe = aura.probe()
    if not probe.configured:
        st.info(probe.message)
    else:
        st.warning(probe.message)
    st.write("Planned actions:")
    st.markdown(
        """
        - Connect with Aura API credentials (`.env`)
        - List Aura instances
        - Directional sync / move with dry-run + verify
        - Aura remains source of truth until sync verified
        """
    )
    if st.button("Probe Aura (stub)"):
        audit("aura.probe", result="stub", detail={"configured": probe.configured})
        st.json(
            {
                "configured": probe.configured,
                "ok": probe.ok,
                "message": probe.message,
                "instances": probe.instances,
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
            ["Instances", "Aura sync", "MCP activate", "Logs & audit"],
            label_visibility="collapsed",
        )
        st.divider()
        st.caption(f"Image pin: `{settings.neo4j_image}`")
        st.caption(f"Data: `{settings.data_dir}`")
        st.caption("Previous Next.js slice is superseded — see README.")

    if page == "Instances":
        page_instances()
    elif page == "Aura sync":
        page_aura()
    elif page == "MCP activate":
        page_mcp()
    else:
        page_logs()


if __name__ == "__main__":
    main()
