# neo4j-database-migration (Neo4j Control)

A utility for moving a Neo4j database between a local Docker instance and a global Neo4j (Aura) database.

Local **Streamlit + Python** app to create, start, stop, and delete isolated **Neo4j Docker** instances. Built as a **PyCharm-friendly** project for **GitHub**.

> **Note:** An earlier Next.js / Origin slice on branch `cursor/neo4j-control-phase0-1-84bb` is **superseded**. This Streamlit app is the primary UI.

Phase 0–1 covers local Docker lifecycle, logging/audit, and MCP placeholders.
**Overview** lists Aura (cloud, if API keys in `.env`), Neo4j Desktop locals, and Docker (running + startable).

---

## Requirements

- Python 3.11+ (`python3` on macOS)
- Docker Engine + Compose v2 (for start/stop; optional for create/list definitions)
- PyCharm Professional or Community (optional)

---

## Quick start (macOS / Linux terminal)

Use a **venv** and an **editable install** so `import neo4j_control` works. Always launch Streamlit with **`python -m streamlit`** from that venv (avoids the system Frameworks Streamlit).

```bash
cd /path/to/neo4j-database-migration
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m pip install -U pip
python -m pip install -e .                # installs deps + this package
cp -n .env.example .env                   # edit if needed
python -m streamlit run app.py --server.port 8517 --server.address 127.0.0.1
```

Open **[http://127.0.0.1:8517](http://127.0.0.1:8517)**.

Equivalent launcher after install: `neo4j-control` or `python -m neo4j_control`.

### Why `pip install -e .` and `app.py`?

`streamlit run neo4j_control/streamlit_app.py` puts `neo4j_control/` on `sys.path`, so `from neo4j_control...` fails unless the package is installed. Running **`app.py` from the repo root** (plus editable install) fixes that.

---

## Open in PyCharm (macOS)

1. **File → Open** the clone root (`neo4j-database-migration`, contains `README.md`, `app.py`, `neo4j_control/`).
2. Interpreter: **Settings → Project → Python Interpreter → Add → Virtualenv**  
   - Base: `/usr/bin/python3` or Homebrew `python3` (3.11+)  
   - Location: project `.venv`
3. In the **PyCharm terminal** (venv active — prompt shows `(.venv)`):

```bash
python -m pip install -U pip
python -m pip install -e .
cp -n .env.example .env
```

4. **Run → Edit Configurations → + → Python**:
   - **Module name:** `streamlit` (select the Module name radio)
   - **Parameters:** `run app.py --server.port 8517 --server.address 127.0.0.1`
   - **Working directory:** project root (folder with `app.py`)
   - **Python interpreter:** the project `.venv` (not system 3.11 Frameworks)
5. Run / Debug.

Confirm the run config uses `.venv` (`which python` / `which streamlit` inside the run should point under `.venv`).

---

## After `git pull` (fix imports)

If the traceback still says `neo4j_control/streamlit_app.py`, **line 9**, and
`/Library/Frameworks/Python.framework/.../streamlit`, you are on an **old checkout**
and/or the **system** Streamlit — not the project venv.

```bash
cd /path/to/neo4j-database-migration
git pull origin main                      # or: git pull
python3 -m venv .venv                     # once
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
python -m streamlit run app.py --server.port 8517 --server.address 127.0.0.1
```

One-liner after pull: `./run_app.sh`

Confirm: `which python` and `which streamlit` both end with `.venv/bin/...` (not Frameworks).

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
app.py                      # preferred Streamlit entrypoint (repo root)
pyproject.toml              # pip install -e .
neo4j_control/
  streamlit_app.py          # UI (also path-bootstraps repo root)
  config.py
  logging_setup.py
  audit.py
  models.py
  services/
  templates/docker-compose.yml
docs/
  OPS-LOCAL.md
  SECURITY.md
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
- This workspace may also have Cursor `origin` — leave it alone; push with remote `github`.

Do **not** commit `.env`, stack `.env` files, or `logs/`.

---

## License

Private / use as you like for local ops tooling.
