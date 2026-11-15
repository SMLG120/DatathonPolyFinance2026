"""Service tests: no network, no AWS. Run from the repository root with

    uv run --no-project --with pytest --with boto3 pytest backend/tests/service -q
"""

import io
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
