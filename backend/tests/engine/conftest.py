"""Engine tests: no network, no AWS, no model. Run from the repository root with

    uv run --no-project --python 3.14 --with pytest pytest backend/tests/engine -q

The engine is imported as ``backend.engine`` (repository root on the path) and
uses the shared contracts package from ``contracts/python``.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT, Path(__file__).resolve().parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
