"""Streamlit entrypoint at the project root.

After ``pip install -e .`` (from the repo root):

    python -m streamlit run app.py --server.port 8517 --server.address 127.0.0.1

Prefer this over ``streamlit run neo4j_control/streamlit_app.py``, which puts the
package directory on ``sys.path`` and breaks ``import neo4j_control`` unless the
package is installed editable (or ``PYTHONPATH`` includes the repo root).
"""

from neo4j_control.streamlit_app import main

main()
