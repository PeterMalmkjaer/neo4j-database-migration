"""On-demand host MCP activation — Phase 4 stub."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class McpStatus:
    active: bool
    target_bolt: str | None
    message: str


class McpActivator:
    """Host-side MCP helper (outside Docker).

    Phase 0–1: UI placeholders only. Real activate/deactivate lands in Phase 4.
    """

    def __init__(self) -> None:
        self._active_for: str | None = None

    def status(self, bolt_uri: str | None = None) -> McpStatus:
        if self._active_for:
            return McpStatus(
                active=True,
                target_bolt=self._active_for,
                message=f"MCP marked active for {self._active_for} (stub — no process started).",
            )
        return McpStatus(
            active=False,
            target_bolt=bolt_uri,
            message="MCP inactive. Phase 4 will start a host MCP process targeting bolt://localhost:<port>.",
        )

    def activate(self, bolt_uri: str) -> McpStatus:
        self._active_for = bolt_uri
        return McpStatus(
            active=True,
            target_bolt=bolt_uri,
            message=(
                f"Placeholder: would activate host MCP → {bolt_uri}. "
                "Not started in Phase 0–1."
            ),
        )

    def deactivate(self) -> McpStatus:
        self._active_for = None
        return McpStatus(
            active=False,
            target_bolt=None,
            message="Placeholder: MCP deactivated (stub).",
        )
