"""Independent validation suite for "Before You Buy" (owner: independent-validator, A4).

Run from the repository root:

    uv run --no-project --python 3.14 --with pytest --with boto3 --with jsonschema pytest validation -q

Rules of this suite:

* production packages are imported because they are the subject under test
  (``backend.*`` and the validators in ``contracts/python/byb_contracts``);
* nothing is imported from ``backend/tests``, ``contracts/python/tests`` or the
  contracts' ``reference_calc``/``tools``: loaders, universes, fakes and the
  reference arithmetic live in ``validation/support`` and were written
  separately, so a bug is not shared;
* no network, no AWS, no model. Every AWS client is a fake from
  ``validation/support/fakes.py``;
* a test that exposes a real defect stays in the suite as
  ``xfail(strict=True, reason="V-id: ...")``; it fails loudly once the defect
  is fixed, which tells the lead to remove the mark.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


def pytest_configure(config):
    config.addinivalue_line("markers", "vcase(case_id): independently labelled validation case id (V01 ...)")
