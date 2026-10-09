"""Aura API client — list cloud instances when credentials are configured."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


@dataclass
class AuraProbeResult:
    configured: bool
    ok: bool
    message: str
    instances: list[dict[str, Any]]


class AuraClient:
    """Neo4j Aura management API (client-credentials).

    Without credentials: no network calls. With credentials: token + list instances.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_base: str | None = None,
        token_url: str | None = None,
    ) -> None:
        self.client_id = client_id or os.getenv("AURA_CLIENT_ID") or ""
        self.client_secret = client_secret or os.getenv("AURA_CLIENT_SECRET") or ""
        self.api_base = (api_base or os.getenv("AURA_API_BASE") or "https://api.neo4j.io/v1").rstrip(
            "/"
        )
        self.token_url = token_url or os.getenv(
            "AURA_TOKEN_URL", "https://api.neo4j.io/oauth/token"
        )

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _token(self) -> str:
        body = parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode()
        req = request.Request(
            self.token_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with request.urlopen(req, timeout=30) as resp:
            import json

            data = json.loads(resp.read().decode())
        token = data.get("access_token")
        if not token:
            raise RuntimeError("Aura token response missing access_token")
        return str(token)

    def _get_json(self, path: str, token: str) -> Any:
        import json

        url = f"{self.api_base}{path}"
        req = request.Request(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            method="GET",
        )
        with request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode())

    def probe(self) -> AuraProbeResult:
        if not self.configured:
            return AuraProbeResult(
                configured=False,
                ok=False,
                message=(
                    "Aura credentials not configured. Set AURA_CLIENT_ID and "
                    "AURA_CLIENT_SECRET in .env (Aura Console → Account → API keys), "
                    "or open https://console.neo4j.io to browse cloud instances."
                ),
                instances=[],
            )
        try:
            token = self._token()
            raw = self._get_json("/instances", token)
            items = raw.get("data", raw if isinstance(raw, list) else [])
            instances: list[dict[str, Any]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                instances.append(
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "status": item.get("status") or item.get("instance_status"),
                        "connection_url": item.get("connection_url")
                        or item.get("bolt_url")
                        or item.get("connectionUrl"),
                        "region": item.get("region"),
                        "memory": item.get("memory"),
                        "type": item.get("type") or item.get("cloud_provider"),
                        "raw": item,
                    }
                )
            return AuraProbeResult(
                configured=True,
                ok=True,
                message=f"Aura API OK — {len(instances)} instance(s).",
                instances=instances,
            )
        except error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode()[:500]
            except Exception:  # noqa: BLE001
                pass
            return AuraProbeResult(
                configured=True,
                ok=False,
                message=f"Aura API HTTP {exc.code}: {body or exc.reason}",
                instances=[],
            )
        except Exception as exc:  # noqa: BLE001
            return AuraProbeResult(
                configured=True,
                ok=False,
                message=f"Aura API error: {exc}",
                instances=[],
            )

    def list_instances(self) -> list[dict[str, Any]]:
        return self.probe().instances
