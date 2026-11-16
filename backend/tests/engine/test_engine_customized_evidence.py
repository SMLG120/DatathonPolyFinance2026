"""Evidence of a customized fictional portfolio (code review F4).

The starting cash and position weights of a portfolio the user edited are still fictional, but they are the
user's numbers. The engine is told so (``portfolio_customized=True``) and says it on those evidence records.
Nothing else may change: no figure, no status, no other record.
"""

import copy

from byb_contracts import validate_check_result

from backend import engine
from backend.engine.check import CUSTOMIZED_WEIGHT_ASSUMPTION
from engine_helpers import case, universe

START = {"cash_weight", "position_weight"}


def _run(**kwargs):
    fixture = case("R1")
    data = universe(fixture["universe"])
    inputs = fixture["inputs"]
    return engine.check_rules(inputs["portfolio"], inputs["policy"], inputs["purchase_request"], data["instruments"], data["holdings"],
                              data["market_data"], data["controversies"], **kwargs)


def _starting_weight_records(result):
    return [record for record in result["evidence"]
            if record["metric_id"] in START and record["subject"]["portfolio_state"] == "STARTING" and record["label"] == "FICTIONAL_SCENARIO"]


def test_scenario_portfolio_weights_carry_no_customization_note():
    result = _run()
    assert result == _run(portfolio_customized=False), "the default is the scenario portfolio"
    records = _starting_weight_records(result)
    assert len(records) >= 2
    assert all(CUSTOMIZED_WEIGHT_ASSUMPTION not in record["assumptions"] for record in records)


def test_customized_portfolio_weights_say_the_user_entered_them_and_nothing_else_changes():
    plain, customized = _run(), _run(portfolio_customized=True)
    validate_check_result(customized)
    records = _starting_weight_records(customized)
    assert len(records) == len(_starting_weight_records(plain)) >= 2
    assert all(CUSTOMIZED_WEIGHT_ASSUMPTION in record["assumptions"] for record in records)
    assert {record["metric_id"] for record in records} == START  # the cash and every held position

    # Only those records differ, and only by that sentence: every figure, status and other record is identical.
    stripped = copy.deepcopy(customized)
    touched = 0
    for record in stripped["evidence"]:
        if CUSTOMIZED_WEIGHT_ASSUMPTION in record["assumptions"]:
            record["assumptions"].remove(CUSTOMIZED_WEIGHT_ASSUMPTION)
            touched += 1
    assert touched == len(records)
    assert stripped == plain
    # The hypothetical purchase keeps its own note and does not gain this one.
    target = next(r for r in customized["evidence"] if r["metric_id"] == "position_weight" and r["subject"]["portfolio_state"] == "PROPOSED")
    assert CUSTOMIZED_WEIGHT_ASSUMPTION not in target["assumptions"]
