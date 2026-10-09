"""Bolt readiness probe for a local Neo4j instance."""

from __future__ import annotations

import socket
import time
from typing import Callable

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def bolt_ready(
    bolt_uri: str,
    password: str,
    *,
    user: str = "neo4j",
    timeout_s: float = 60.0,
    poll_s: float = 2.0,
    on_attempt: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """
    Wait until Bolt accepts auth and a trivial query.
    Returns (ok, message).
    """
    deadline = time.monotonic() + timeout_s
    last = "not started"
    while time.monotonic() < deadline:
        try:
            driver = GraphDatabase.driver(bolt_uri, auth=(user, password))
            try:
                driver.verify_connectivity()
                with driver.session() as session:
                    session.run("RETURN 1 AS n").single()
                if on_attempt:
                    on_attempt("ready")
                return True, "Bolt ready"
            finally:
                driver.close()
        except (ServiceUnavailable, Neo4jError, OSError) as exc:
            last = str(exc)
            if on_attempt:
                on_attempt(last)
        time.sleep(poll_s)
    return False, f"Bolt not ready within {timeout_s:.0f}s: {last}"


def bolt_ready_once(bolt_uri: str, password: str, user: str = "neo4j") -> tuple[bool, str]:
    return bolt_ready(bolt_uri, password, user=user, timeout_s=0.1, poll_s=0.05)
