# Local operations — Neo4j Control

## Prerequisites

- Python 3.11+
- Docker Engine + Docker Compose v2 (for start/stop/delete with volumes)
- PyCharm (optional but recommended)

Install from the repo root with a venv:

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e .
python -m streamlit run app.py --server.port 8517 --server.address 127.0.0.1
```

Without Docker you can still **create**, **list**, and **delete definitions** (compose files + `data/instances.json`). Start/stop require Docker.

## Create an instance

1. Open the Streamlit **Instances** page.
2. Enter a name (`demo-local`) and password (≥ 8 chars).
3. Optionally check **Start after create**.
4. Confirm the new row shows Bolt/HTTP ports and status `defined` or `running`.

Each instance gets:

- `data/stacks/<name>/docker-compose.yml` (from pinned template)
- `data/stacks/<name>/.env` (ports, image, `NEO4J_AUTH` — gitignored)
- Registry entry in `data/instances.json`

## Start / stop

- **Start** runs `docker compose up -d` in the stack dir, then probes Bolt (`RETURN 1`) when the driver can connect.
- **Stop** runs `docker compose stop` (volumes retained).

## Delete (typed confirm)

1. Expand **Delete `<name>`**.
2. Type the exact instance name.
3. Choose whether to remove Docker volumes (default: yes).
4. Click **Delete permanently**.

This runs `docker compose down [-v]`, removes the stack directory, and drops the registry entry. An audit line is appended to `logs/audit.log`.

## Ports

Default bases (from `.env` / `.env.example`):

| Service | Base |
|---------|------|
| Bolt | 7687 |
| HTTP | 7474 |

Each additional instance adds +10 to both ports.

## Image pin

`NEO4J_IMAGE=neo4j:5.26.0` (override in project `.env` or per-stack `.env`).

## Logs

| File | Purpose |
|------|---------|
| `logs/app.log` | Structured app log (rotating) |
| `logs/audit.log` | Append-only JSON Lines audit trail |

## CLI smoke (optional)

```bash
# From project root, with venv active
python -c "from neo4j_control.services.docker_neo4j import Neo4jDockerService; \
s=Neo4jDockerService(); print([i.name for i in s.list_instances()])"
```
