"""Service tests: no network, no AWS. Run from the repository root with

    uv run --no-project --with pytest --with boto3 pytest backend/tests/service -q
"""

import io
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
# The repository root (``backend``), the shared contracts package (``byb_contracts``) and this folder (the fakes).
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT, Path(__file__).resolve().parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from backend.common import log  # noqa: E402


@pytest.fixture(autouse=True)
def captured_log():
    """Every test gets a private log stream; tests can assert on its lines."""
    stream = io.StringIO()
    log.configure("INFO", stream)
    log.bind()
    yield stream
    log.configure("INFO", None)
    log.bind()
