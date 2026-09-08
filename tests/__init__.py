"""Make src/ importable so tests can `import main`, `import config`, ...

Run from the repo root:  python3 -m unittest discover -s tests -t .
"""
import os
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Point config.DATA_DIR at a throwaway dir before config is ever imported, so no test
# that reaches a data-dir write (state.json, the agent log, ...) can poison the real
# data/ of a live deployment sharing this checkout. Individual modules still override
# config.STATE_PATH; this is the backstop for everything else.
os.environ.setdefault("CODEBOT_DATA_DIR", tempfile.mkdtemp(prefix="codebot-test-data-"))
