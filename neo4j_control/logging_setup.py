"""Structured application logging to logs/app.log (+ console)."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from neo4j_control.config import Settings, ensure_runtime_dirs

_CONFIGURED = False


def setup_logging(settings: Settings | None = None) -> logging.Logger:
    global _CONFIGURED
    settings = ensure_runtime_dirs(settings)
    logger = logging.getLogger("neo4j_control")
    if _CONFIGURED:
        return logger

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    file_handler = RotatingFileHandler(
        settings.app_log_path,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console)
    logger.propagate = False
    _CONFIGURED = True
    logger.info("Logging initialized → %s", settings.app_log_path)
    return logger


def get_logger(name: str = "neo4j_control") -> logging.Logger:
    return logging.getLogger(name)
