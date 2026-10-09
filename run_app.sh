#!/usr/bin/env bash
# Launch Neo4j Control with the project venv (macOS/Linux).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
[[ -f .env ]] || cp .env.example .env

exec python -m streamlit run app.py --server.port 8517 --server.address 127.0.0.1
