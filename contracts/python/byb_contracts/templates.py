"""Deterministic text templates shared by the service and the fixtures. Standard library only.

``scope_description`` is the text printed on a rule card. It is rendered from
the rule's type and parameters, never written by a model.
"""

from __future__ import annotations

from .constants import SCENARIOS

OUT_OF_SCOPE_NOTE = "Bond funds, commodity funds and crypto assets are outside this rule's scope and are not assessed."
LOOK_THROUGH = "direct holdings plus look-through via equity funds, share classes of one company added together"

DISCLOSURES = (
    "Simulation only: fictional portfolio, no real transaction, not personalized financial advice.",
    "The purchase is funded from existing cash; every other position is unchanged. Selling, shorting and leverage are not supported.",
    "Fees and taxes are excluded.",
    "Fund look-through uses a dated holdings snapshot; it is not the fund's historical composition.",
    "Historical replays describe the past. They are not forecasts and do not guarantee future results.",
)

EXPOSURE_SELECTION_NOTE = (
    "Shown: the company being bought, companies named by a rule or causing a breach, then the largest company exposures "
    "after the purchase. At most 10 companies, largest first."
)


def scope_description(rule_type: str, parameters: dict) -> str:
    if rule_type == "max_issuer_exposure":
        scope = parameters["issuer_scope"]
        subject = "any single company" if scope == "any" else f"the company {scope}"
        return f"Maximum total equity exposure to {subject}: {LOOK_THROUGH}. {OUT_OF_SCOPE_NOTE}"
    if rule_type == "min_issuer_exposure":
        return f"Minimum total equity exposure to the company {parameters['issuer_id']}: {LOOK_THROUGH}. {OUT_OF_SCOPE_NOTE}"
    if rule_type == "exclusion":
        definition = parameters["definition"]
        if definition["kind"] == "named_issuers":
            names = ", ".join(definition["issuer_ids"])
            return f"Maximum total equity exposure to the named companies ({names}): {LOOK_THROUGH}. {OUT_OF_SCOPE_NOTE}"
        return (
            f"Maximum total equity exposure to holdings labelled '{definition['sector']}': the sector label reported in the "
            "fund issuer's holdings file for fund constituents, the instrument registry label for direct holdings. "
            "Constituents without a label count as unknown, not as zero. A sector label is not a list of oil producers "
            f"and is not a controversy finding. {OUT_OF_SCOPE_NOTE}"
        )
    if rule_type == "controversy_exclusion":
        criteria = parameters["criteria"]
        natures = ", ".join(criteria["natures"])
        since = f" dated on or after {criteria['event_date_from']}" if criteria["event_date_from"] else ""
        return (
            f"Maximum total equity exposure to companies with a controversy-registry record of nature {natures}{since}. "
            "Companies without a record are not assessed: absence from the registry is unknown, never a pass. "
            f"{OUT_OF_SCOPE_NOTE}"
        )
    if rule_type == "scenario_loss_budget":
        scenario = SCENARIOS[parameters["scenario_id"]]
        return (
            f"Maximum terminal loss of the evaluated allocation replayed from {scenario['base_date']} to {scenario['end_date']} "
            "(buy and hold, cash earning 0, in CAD). This replays an assumed allocation through history: it is not a "
            "forecast and not a maximum future loss. Drawdown inside the period is reported separately and is not part of this rule."
        )
    raise ValueError(f"unknown rule_type {rule_type!r}")
