"""Application configuration loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of the neo4j_control package
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _path(env_key: str, default: str) -> Path:
    raw = os.getenv(env_key, default)
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    logs_dir: Path
    stacks_dir: Path
    registry_path: Path
    neo4j_image: str
    default_password: str
    bolt_port_base: int
    http_port_base: int
    streamlit_port: int
    streamlit_address: str

    @property
    def app_log_path(self) -> Path:
        return self.logs_dir / "app.log"

    @property
    def audit_log_path(self) -> Path:
        return self.logs_dir / "audit.log"


def get_settings() -> Settings:
    data_dir = _path("NEO4J_CONTROL_DATA_DIR", "data")
    logs_dir = _path("NEO4J_CONTROL_LOGS_DIR", "logs")
    stacks_dir = _path("NEO4J_CONTROL_STACKS_DIR", "data/stacks")
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        logs_dir=logs_dir,
        stacks_dir=stacks_dir,
        registry_path=data_dir / "instances.json",
        neo4j_image=os.getenv("NEO4J_IMAGE", "neo4j:5.26.0"),
        default_password=os.getenv("NEO4J_DEFAULT_PASSWORD", "changeme-local-only"),
        bolt_port_base=int(os.getenv("NEO4J_BOLT_PORT_BASE", "7687")),
        http_port_base=int(os.getenv("NEO4J_HTTP_PORT_BASE", "7474")),
        streamlit_port=int(os.getenv("STREAMLIT_SERVER_PORT", "8517")),
        streamlit_address=os.getenv("STREAMLIT_SERVER_ADDRESS", "127.0.0.1"),
    )


def ensure_runtime_dirs(settings: Settings | None = None) -> Settings:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.stacks_dir.mkdir(parents=True, exist_ok=True)
    return settings
