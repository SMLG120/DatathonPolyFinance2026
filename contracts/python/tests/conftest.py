"""Make ``byb_contracts`` and the test helpers importable without installing anything."""

import sys
from pathlib import Path

PYTHON_DIR = Path(__file__).resolve().parents[1]
for extra in (PYTHON_DIR, PYTHON_DIR / "tests", PYTHON_DIR / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
