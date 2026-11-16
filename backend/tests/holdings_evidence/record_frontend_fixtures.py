"""Records the investigator's answers on the SYNTHETIC contract universes, for the interface's test-data mode.

    uv run --no-project --python 3.14 --with boto3 python backend/tests/holdings_evidence/record_frontend_fixtures.py

Writes ``frontend/src/components/evidence-investigator/recorded-answers.json``. Every answer is the real output of
``backend.api.holdings_evidence.investigate`` (server wording, no model) on invented, hand-checkable numbers; nothing is
typed by hand. ``test_recorded_frontend_answers_are_current`` fails when the file is stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from backend.api.holdings_evidence import investigate  # noqa: E402
from backend.api.holdings_evidence.wording import OVERVIEW_QUESTION, SUGGESTED_QUESTIONS  # noqa: E402

TARGET = REPO_ROOT / "frontend" / "src" / "components" / "evidence-investigator" / "recorded-answers.json"
PERSONAS = ("robert", "mateo")  # the personas that have a synthetic universe


def build() -> dict:
    answers: dict = {}
    for persona_id in PERSONAS:
        universe = json.loads((REPO_ROOT / "contracts" / "fixtures" / "engine" / f"{persona_id}_synthetic_universe.json").read_text(encoding="utf-8"))
        scenario = json.loads((REPO_ROOT / "contracts" / "scenarios" / f"{persona_id}.json").read_text(encoding="utf-8"))
        registry = universe["instruments"]["instruments"]
        snapshot = SimpleNamespace(snapshot_id=f"synthetic-{persona_id}", registry=registry, instruments=universe["instruments"],
                                   holdings=universe["holdings"], sources=universe["sources"])
        funds = [p["instrument_id"] for p in scenario["portfolio"]["positions"] if registry[p["instrument_id"]]["equity_scope"] and registry[p["instrument_id"]]["is_fund"]]
        for fund_id in [None] + funds:
            def ask(question: str) -> dict:
                return investigate(snapshot=snapshot, scenario=scenario, policy=None, fund_id=fund_id, question=question)

            # One full answer per scope (the overview); every other question stores only the members that differ from it.
            base = ask(OVERVIEW_QUESTION)
            scope = f"{persona_id}|{fund_id or '*'}"
            answers[scope] = {"base": base, "by_question": {
                question: {key: value for key, value in ask(question).items() if base.get(key) != value} for question in SUGGESTED_QUESTIONS}}
    return {
        "generated_by": "backend/tests/holdings_evidence/record_frontend_fixtures.py — do not edit by hand",
        "synthetic": True,
        "note": "Answers of the evidence investigator on the synthetic contract universes (invented numbers, not market data).",
        "overview_question": OVERVIEW_QUESTION,
        "questions": list(SUGGESTED_QUESTIONS),
        "answers": answers,
    }


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPO_ROOT)} ({TARGET.stat().st_size} bytes)")
