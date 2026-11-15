"""Loaders for the real (git-ignored) data files. A missing file is an explicit skip, never a silent pass."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"
STARTER = REPO_ROOT / "data" / "starter"


def need(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"real data file not present in this checkout (git-ignored, copy it in): {path.relative_to(REPO_ROOT)}")
    return path


@lru_cache(maxsize=None)
def _json(name: str) -> dict:
    return json.loads((PROCESSED / name).read_text(encoding="utf-8"))


def processed(name: str) -> dict:
    need(PROCESSED / name)
    return _json(name)


def real_universe() -> dict:
    return {
        "instruments": processed("instruments.json"),
        "holdings": processed("holdings.json"),
        "market_data": processed("market_data.json"),
        "controversies": processed("controversies.json"),
    }


# LEAD_DECISIONS D7 (fictional portfolios, typed in here by the validator from the document).
ROBERT = {"cash": 0.30, "positions": {"XBB.TO": 0.30, "SPY": 0.20, "XIU.TO": 0.10, "RY.TO": 0.05, "JNJ": 0.05}}
MATEO = {"cash": 0.25, "positions": {"XBB.TO": 0.25, "XIU.TO": 0.20, "ESGV": 0.15, "MSFT": 0.05, "CNR.TO": 0.05, "FTS.TO": 0.05}}
