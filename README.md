# neo4j-database-migration (Neo4j Control)

A utility for moving a Neo4j database between a local Docker instance and a global Neo4j (Aura) database.

Local **Streamlit + Python** app to create, start, stop, and delete isolated **Neo4j Docker** instances. Built as a **PyCharm-friendly** project for **GitHub**.

> **Note:** An earlier Next.js / Origin slice on branch `cursor/neo4j-control-phase0-1-84bb` is **superseded**. This Streamlit app is the primary UI.

Phase 0–1 covers local Docker lifecycle, logging/audit, and UI placeholders for Aura sync and MCP activate. Aura credentials are **not** required yet.

---

## Requirements

- Python 3.11+
- Docker Engine + Compose v2 (for start/stop; optional for create/list definitions)
- PyCharm Professional or Community (optional)

---

## Quick start (terminal)

```bash
cd /path/to/neo4j-control
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # edit if needed
streamlit run neo4j_control/streamlit_app.py --server.port 8517 --server.address 127.0.0.1
```

Open **[http://127.0.0.1:8517](http://127.0.0.1:8517)**.

---

## Open in PyCharm

1. **File → Open** the project root (folder containing `README.md` and `neo4j_control/`).
2. Create a venv: **Settings → Project → Python Interpreter → Add → Virtualenv** (or use existing `.venv`).
3. Install deps: in the PyCharm terminal run `pip install -r requirements.txt`.
4. Add a **Streamlit** run configuration:
   - **Run → Edit Configurations → + → Python**
   - **Module name:** `streamlit` (enable “Module name” radio)  
     *or* **Script path:** path to `streamlit` in `.venv/bin/streamlit`
   - **Parameters:** `run neo4j_control/streamlit_app.py --server.port 8517 --server.address 127.0.0.1`
   - **Working directory:** project root
   - **Python interpreter:** the project venv
5. Run / Debug that configuration.

Optional: mark `neo4j_control` as a sources root if imports are not resolved (usually unnecessary when working directory is the project root).

---

## What works without Docker vs with Docker

| Action | Without Docker | With Docker |
|--------|----------------|-------------|
| List instances | Yes (registry) | Yes (+ live status) |
| Create definition (compose + registry) | Yes | Yes |
| Start / Stop | No (clear error) | Yes |
| Bolt readiness check | N/A | Yes after start |
| Delete (typed confirm) | Removes files + registry | Also `compose down -v` |

---

## Layout

```
neo4j_control/
  streamlit_app.py          # UI entrypoint
  config.py                 # .env / paths
  logging_setup.py          # logs/app.log
  audit.py                  # logs/audit.log (JSONL)
  models.py
  services/
    registry.py             # data/instances.json
    docker_neo4j.py         # Compose lifecycle
    bolt.py                 # readiness probe
    aura.py                 # Phase 2 stub
    mcp.py                  # Phase 4 stub
  templates/
    docker-compose.yml      # pinned Neo4j image via env
docs/
  OPS-LOCAL.md
  SECURITY.md
.data / logs / stacks       # runtime (gitignored)
```

---

## Configuration

Copy `.env.example` → `.env`. Important keys:

- `NEO4J_IMAGE=neo4j:5.26.0` — pinned image tag
- `STREAMLIT_SERVER_PORT=8517`
- `NEO4J_DEFAULT_PASSWORD` — local only; change it

See [docs/SECURITY.md](docs/SECURITY.md) and [docs/OPS-LOCAL.md](docs/OPS-LOCAL.md).

---

## Git remotes

- **GitHub (canonical):** https://github.com/PeterMalmkjaer/neo4j-database-migration  
  Remote name in this workspace: `github`
- **Origin/Cursor** may also exist as `origin` for the cloud agent — leave it alone.

```bash
git remote add github https://github.com/PeterMalmkjaer/neo4j-database-migration.git
git push -u github cursor/neo4j-control-streamlit-05cc
# Usable default branch (new repo / Initial-commit only):
git push -u github HEAD:main
```

Do **not** commit `.env`, stack `.env` files, or `logs/`.

---

## License

Private / use as you like for local ops tooling.
