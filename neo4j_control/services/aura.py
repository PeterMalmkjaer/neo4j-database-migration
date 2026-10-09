"""Aura API client — Phase 2 stub (no live credentials required for Phase 0–1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AuraProbeResult:
    configured: bool
    ok: bool
    message: str
    instances: list[dict[str, Any]]


class AuraClient:
    """Placeholder for Neo4j Aura management API.

    Phase 0–1: report that Aura is not configured. Do not call the network
    unless credentials are present (future Phase 2).
    """

    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def probe(self) -> AuraProbeResult:
        if not self.configured:
            return AuraProbeResult(
                configured=False,
                ok=False,
                message="Aura credentials not configured (set AURA_CLIENT_ID / AURA_CLIENT_SECRET in Phase 2).",
                instances=[],
            )
        # Phase 2: exchange credentials and list instances
        return AuraProbeResult(
            configured=True,
            ok=False,
            message="Aura API integration not implemented yet (Phase 2).",
            instances=[],
        )

    def list_instances(self) -> list[dict[str, Any]]:
        return self.probe().instances
