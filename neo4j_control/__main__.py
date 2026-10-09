"""Allow `python -m neo4j_control` (launches Streamlit on app.py when possible)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    app = root / "app.py"
    target = str(app if app.exists() else Path(__file__).resolve().parent / "streamlit_app.py")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        target,
        "--server.port",
        "8517",
        "--server.address",
        "127.0.0.1",
    ]
    raise SystemExit(subprocess.call(cmd, cwd=str(root)))


if __name__ == "__main__":
    main()
