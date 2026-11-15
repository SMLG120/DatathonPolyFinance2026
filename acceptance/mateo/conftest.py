"""Mateo acceptance suite (Milestone 6): no network, no AWS, no model.

Run from the repository root:

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest acceptance/mateo -q

The engine is imported read-only as ``backend.engine``; the contract helpers come from ``contracts/python``.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT, HERE):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
