"""Make src/ importable so tests can `import main`, `import config`, ...

Run from the repo root:  python3 -m unittest discover -s tests -t .
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
