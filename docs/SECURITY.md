# Security notes — Neo4j Control

## Secrets

- Never commit `.env` or `data/stacks/*/.env`.
- Stack passwords live only in each stack’s `.env` as `NEO4J_AUTH=neo4j/<password>`.
- The instance registry (`data/instances.json`) stores ports and paths, **not** passwords.
- Aura credentials (Phase 2) belong in `.env` only; Phase 0–1 does not require them.

## Destructive actions

- **Delete** requires typing the exact instance name.
- Default delete removes Docker volumes (`compose down -v`) — local graph data is wiped.
- Prefer stopping instead of deleting when you only need to free CPU/RAM.

## Network exposure

- Streamlit defaults to `127.0.0.1:8517` (not public).
- Neo4j publishes Bolt/HTTP on localhost ports only via Compose port maps.
- Do not bind Streamlit or Neo4j to `0.0.0.0` on untrusted networks without auth in front.

## MCP (future)

- MCP will run **on the host**, targeting `bolt://127.0.0.1:<port>`.
- Activate only while an LLM session needs the DB; deactivate afterward (Phase 4).

## Audit

- Sensitive actions (`create`, `start`, `stop`, `delete`, Aura/MCP stubs) append to `logs/audit.log`.
- Do not put raw passwords in audit `detail` fields.
