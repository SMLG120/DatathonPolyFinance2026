"""Evidence investigator tests: no network, no AWS. Run from the repository root with

    uv run --no-project --python 3.14 --with pytest --with boto3 pytest backend/tests/holdings_evidence -q
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
# The repository root (``backend``), the shared contracts package and the service fakes (FakeS3, FakeBedrock, Service).
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT, REPO_ROOT / "backend" / "tests" / "service", Path(__file__).resolve().parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))
