"""``check_rules``: the full ``check_result`` document.

``analyse`` does every calculation for one purchase request (both portfolio
states, every evaluated rule, the scenario). ``check_rules`` turns that into
the contract document with evidence records and template-rendered text.
The maximum compliant weight lives in ``boundary.py`` and is verified by
calling ``check_rules`` again at the boundary.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from byb_contracts import (
    ContractError,
    DEFAULT_VALUATION_DATE,
    EXPOSURE_TOP_N,
    SCENARIOS,
    SCHEMA_VERSION,
    UNKNOWN_CAUSES,
    derive_summary,
    rule_is_evaluated,
    validate_purchase_request,
)
from byb_contracts.templates import DISCLOSURES, EXPOSURE_SELECTION_NOTE

from . import rules as R
from .core import (
    _Market,
    compute_exposure,
    held_positions,
    public_row,
    records_of,
    refuse_unusable_request,
    registry_of,
    replay_state,
    simulate_change,
)
from .guard import data_problems, non_finite_paths
from .text import eq, num, pct, points, span, total
from .version import CALCULATION_VERSION

STATES = ("starting", "proposed")
SECTOR_LABEL_NOTE = "A sector label is not a list of oil producers and is not a controversy finding."
CONTROVERSY_RECORD_NOTE = "A record says that a dated event is on file with its source; it is not a judgement of the company."
STATE_LABEL = {"starting": "STARTING", "proposed": "PROPOSED"}
STATE_TAG = {"starting": "start", "proposed": "prop"}
STATE_WORDS = {"starting": "before the purchase", "proposed": "after the purchase"}

UNKNOWN_CAUSE_TEXT = {
    "PARTIAL_HOLDINGS": "a held fund reports only part of its holdings",
    "MISSING_HOLDINGS": "no holdings file is held for a fund in the portfolio",
    "UNCLASSIFIED_SECTOR": "some holdings carry no sector label",
    "REGISTRY_ABSENCE": "companies without a matching registry record are not assessed",
    "INSUFFICIENT_HISTORY": "an instrument has no usable price history for the scenario period",
}
UNSOURCED_MARKET_DATA = "Taken from the market data supplied to the engine; no source id was supplied with it."
UNATTRIBUTED_NOTE = "The part of a fund not covered by its holdings file could be any issuer; it is never treated as zero."


# --------------------------------------------------------------------------- analysis (numbers only)

def _scenario_section(sim: dict, market_data: Any, scenario_id: str, requested_id: str) -> tuple[dict, dict]:
    scenario = SCENARIOS[scenario_id]
    base_date, end_date = scenario["base_date"], scenario["end_date"]
    market = _Market(market_data)
    universe = [i for i, _ in held_positions(sim["proposed_portfolio"])]
    histories = {i: market.history(i, base_date, end_date) for i in universe}
    target = histories[requested_id] if requested_id in histories else market.history(requested_id, base_date, end_date)
    missing = [i for i in universe if histories[i] is None]
    states = {state: None for state in STATES}
    if not missing:
        for state in STATES:
            states[state] = replay_state(market, sim[f"{state}_portfolio"], histories, base_date, end_date)
    section = {
        "scenario_id": scenario_id,
        "label": scenario["label"],
        "base_date": base_date,
        "end_date": end_date,
        "status": "INSUFFICIENT_HISTORY" if missing else "COMPUTED",
        "starting": {k: v for k, v in states["starting"].items() if not k.startswith("_")} if states["starting"] else None,
        "proposed": {k: v for k, v in states["proposed"].items() if not k.startswith("_")} if states["proposed"] else None,
        "target_instrument_return": target["return_cad"] if target else None,
        "instrument_returns": [public_row(histories[i]) for i in universe if histories[i] is not None],
        "missing_instruments": missing,
        "assumptions": list(scenario["assumptions"]),
        "evidence_ids": [],
    }
    return section, {"histories": histories, "states": states, "target": target}


def analyse(
    portfolio: dict,
    policy: Optional[dict],
    purchase_request: dict,
    instruments: Any,
    holdings: Any,
    market_data: Any,
    controversies: Any,
    draft_rules: Optional[list] = None,
) -> dict:
    """Every number of one check. ``analysis["ok"]`` is False when the request was not executed."""
    preview = draft_rules is not None
    sim = simulate_change(portfolio, purchase_request, instruments, policy, draft_rules=draft_rules)
    analysis: dict = {"sim": sim, "preview": preview, "ok": sim["execution"]["status"] == "OK"}
    if not analysis["ok"]:
        return analysis

    registry = registry_of(instruments)
    rules = list(draft_rules) if preview else list(policy["rules"])
    evaluated = [rule for rule in rules if rule_is_evaluated(rule, preview)]
    records = records_of(controversies)
    exposure = {state: compute_exposure(sim[f"{state}_portfolio"], registry, holdings) for state in STATES}
    flagged = {
        rule["rule_id"]: R.flagged_issuers(rule["parameters"]["criteria"], records)
        for rule in evaluated if rule["rule_type"] == "controversy_exclusion"
    }

    scenario, replay = None, None
    scenario_rules = [rule for rule in evaluated if rule["rule_type"] == "scenario_loss_budget"]
    if scenario_rules:
        scenario, replay = _scenario_section(sim, market_data, scenario_rules[0]["parameters"]["scenario_id"], purchase_request["instrument_id"])

    results: dict[str, dict] = {}
    for rule in evaluated:
        per_state = {}
        for state in STATES:
            if rule["rule_type"] == "scenario_loss_budget":
                measures = scenario[state]
                bounds = None
                if measures is not None:
                    loss = 0.0 - measures["scenario_terminal_return"]
                    bounds = {"lower": loss, "upper": loss}
                per_state[state] = R.evaluate(rule, bounds, None)
            else:
                bounds = R.exposure_bounds(rule, exposure[state], flagged.get(rule["rule_id"]))
                per_state[state] = R.evaluate(rule, bounds, exposure[state])
        per_state["unknown_causes"] = R.unknown_causes(rule, per_state["proposed"]["bounds"], exposure["proposed"])
        results[rule["rule_id"]] = per_state

    analysis.update({
        "registry": registry,
        "rules": rules,
        "evaluated": evaluated,
        "objectives": list(policy["objectives"]) if policy else [],
        "exposure": exposure,
        "flagged": flagged,
        "scenario": scenario,
        "replay": replay,
        "results": results,
        "conflicts": R.proven_conflicts(evaluated),
    })
    return analysis


# --------------------------------------------------------------------------- evidence

class Evidence:
    """Collects evidence records with deterministic ids; a repeated id returns the first record."""

    def __init__(self, policy_version: Optional[int], valuation_date: str):
        self.records: list[dict] = []
        self._ids: dict[str, str] = {}
        self.policy_version = policy_version
        self.as_of = {"type": "AS_OF", "date": valuation_date}

    def has(self, key: str) -> bool:
        return key in self._ids

    def id(self, key: str) -> str:
        return self._ids[key]

    def record(self, evidence_id: str) -> dict:
        return next(record for record in self.records if record["evidence_id"] == evidence_id)

    def add(self, key: str, label: str, metric_id: str, value: Any, kind: str, subject_id: str, *, state: str = "NOT_APPLICABLE",
            via: Optional[str] = None, unit: str = "fraction", period: Optional[dict] = None, sources: Any = (),
            assumptions: Any = (), derived: Any = (), formula: Optional[str] = None, currency: Optional[str] = None) -> str:
        if key in self._ids:
            return self._ids[key]
        evidence_id = re.sub(r"[^A-Za-z0-9._:-]", "_", key)
        if len(evidence_id) > 120 or evidence_id in self._ids.values():
            evidence_id = f"{evidence_id[:100]}-n{len(self.records)}"
        self._ids[key] = evidence_id
        self.records.append({
            "evidence_id": evidence_id,
            "label": label,
            "metric_id": metric_id,
            "value": value,
            "unit": unit,
            "currency": currency,
            "subject": {"kind": kind, "id": subject_id, "via_fund_id": via, "portfolio_state": state},
            "period": period or self.as_of,
            "source_ids": list(dict.fromkeys(s for s in sources if s)),
            "assumptions": list(assumptions),
            "derived_from": list(dict.fromkeys(d for d in derived if d)),
            "formula": formula,
            "calculation_version": CALCULATION_VERSION,
            "policy_version": self.policy_version,
        })
        return evidence_id


class _Document:
    """Builds the check_result sections from an analysis."""

    def __init__(self, analysis: dict, portfolio: dict, policy: Optional[dict], request: dict, data_sources: Optional[dict]):
        self.a = analysis
        self.portfolio = portfolio
        self.request = request
        self.requested = request["instrument_id"]
        self.registry = analysis["registry"]
        self.exposure = analysis["exposure"]
        self.sim = analysis["sim"]
        self.portfolio_id = portfolio["portfolio_id"]
        self.sources = data_sources or {}
        self.ev = Evidence(None if analysis["preview"] or policy is None else policy["version"], portfolio["valuation_date"])
        self.names: dict[str, tuple[str, str]] = {}
        for instrument_id, instrument in self.registry.items():
            known = self.names.get(instrument["issuer_id"])
            if known is None or instrument_id < known[0]:
                self.names[instrument["issuer_id"]] = (instrument_id, instrument["name"])
        self.fund_info = {}
        for state in STATES:
            for fund in self.exposure[state]["funds"]:
                self.fund_info[fund["fund_id"]] = fund
        self._weights()

    # ----- names

    def issuer_name(self, issuer: str) -> str:
        if issuer in self.names:
            return self.names[issuer][1]
        for state in STATES:
            if issuer in self.exposure[state]["row_names"]:
                return self.exposure[state]["row_names"][issuer]
        return issuer

    # ----- portfolio weights

    def _weights(self) -> None:
        feasibility = self.sim["feasibility"]
        self.ev.add("ev-cash-start", "FICTIONAL_SCENARIO", "cash_weight", feasibility["cash_before"], "PORTFOLIO", self.portfolio_id, state="STARTING")
        for instrument_id, weight in held_positions(self.sim["starting_portfolio"]):
            self.ev.add(f"ev-w-{instrument_id}-start", "FICTIONAL_SCENARIO", "position_weight", weight, "INSTRUMENT", instrument_id, state="STARTING")
        start = self.ev.add(f"ev-w-{self.requested}-start", "FICTIONAL_SCENARIO", "position_weight", feasibility["starting_direct_weight"], "INSTRUMENT", self.requested, state="STARTING")
        target = self.ev.add(
            f"ev-w-{self.requested}-target", "FICTIONAL_SCENARIO", "position_weight", feasibility["target_direct_weight"], "INSTRUMENT", self.requested,
            state="PROPOSED", assumptions=["Hypothetical purchase requested by the user; not executed."],
        )
        self.ev.add(
            "ev-cash-after", "CALCULATION", "cash_after_purchase", feasibility["cash_after"], "PORTFOLIO", self.portfolio_id, state="PROPOSED",
            assumptions=["Funded from cash; every other position unchanged; fees and taxes excluded."],
            derived=["ev-cash-start", start, target],
            formula=f"{num(feasibility['cash_before'])} - ({num(feasibility['target_direct_weight'])} - {num(feasibility['starting_direct_weight'])}) {eq(feasibility['cash_after'])}",
        )

    def weight_ev(self, instrument_id: str, state: str) -> str:
        if instrument_id == self.requested and state == "proposed":
            return self.ev.id(f"ev-w-{instrument_id}-target")
        return self.ev.id(f"ev-w-{instrument_id}-start")

    def cash_ev(self, state: str) -> str:
        return "ev-cash-start" if state == "starting" else "ev-cash-after"

    def scope_weight_evs(self, state: str) -> list[str]:
        ids = [self.weight_ev(i, state) for i, _ in held_positions(self.sim[f"{state}_portfolio"]) if self.registry[i]["equity_scope"]]
        return ids or [self.cash_ev(state)]

    # ----- funds

    def coverage_ev(self, fund_id: str) -> str:
        fund = self.fund_info[fund_id]
        if fund["status"] == "MISSING":
            return self.ev.add(
                f"ev-cov-{fund_id}", "ASSUMPTION", "fund_coverage_fraction", 0.0, "FUND", fund_id,
                assumptions=["No holdings file is held for this fund: its whole weight is unknown exposure, never zero exposure."],
            )
        period = {"type": "AS_OF", "date": fund["holdings_date"]}
        self.ev.add(f"ev-hdate-{fund_id}", "FACT", "holdings_date", fund["holdings_date"], "FUND", fund_id, unit="date", period=period, sources=[fund["source_id"]])
        return self.ev.add(
            f"ev-cov-{fund_id}", "CALCULATION", "fund_coverage_fraction", fund["coverage_fraction"], "FUND", fund_id, period=period,
            sources=[fund["source_id"]], assumptions=["Reported weights are summed as published; nothing is rescaled."],
            formula=f"sum of the reported constituent weights {eq(fund['coverage_fraction'])}",
        )

    def unattributed_evs(self, state: str) -> list[str]:
        ids = []
        for fund in self.exposure[state]["funds"]:
            fund_id = fund["fund_id"]
            ids.append(self.ev.add(
                f"ev-unattr-{fund_id}-{STATE_TAG[state]}", "CALCULATION", "unattributed_fund_weight", fund["uncovered_portfolio_weight"], "FUND", fund_id,
                state=STATE_LABEL[state], assumptions=[UNATTRIBUTED_NOTE], derived=[self.weight_ev(fund_id, state), self.coverage_ev(fund_id)],
                formula=f"{num(fund['portfolio_weight'])} x max(0, 1 - {num(fund['coverage_fraction'])}) {eq(fund['uncovered_portfolio_weight'])}",
            ))
        return ids

    # ----- issuers

    def issuer_evs(self, issuer: str, state: str) -> tuple[str, str]:
        """(lower id, upper id) for one issuer in one state, with the path records behind them."""
        tag = STATE_TAG[state]
        lower_key, upper_key = f"ev-lo-{issuer}-{tag}", f"ev-up-{issuer}-{tag}"
        if self.ev.has(lower_key):
            return self.ev.id(lower_key), self.ev.id(upper_key)
        exposure = self.exposure[state]
        label = STATE_LABEL[state]
        derived, terms = [], []
        direct = exposure["direct"].get(issuer, 0.0)
        if direct > 0:
            held = [(p["position_id"], p["weight"]) for p in exposure["paths"] if p["kind"] == "DIRECT" and p["issuer_id"] == issuer]
            derived.append(self.ev.add(
                f"ev-dir-{issuer}-{tag}", "CALCULATION", "issuer_direct_exposure", direct, "ISSUER", issuer, state=label,
                derived=[self.weight_ev(i, state) for i, _ in held],
                formula=f"{total([w for _, w in held])} {eq(direct)}" + (" (share classes of one company added together)" if len(held) > 1 else ""),
            ))
            terms.append(direct)
        for fund_id, known in exposure["via_fund"].get(issuer, {}).items():
            fund = self.fund_info[fund_id]
            rows = [p for p in exposure["paths"] if p["kind"] == "FUND" and p["position_id"] == fund_id and p["issuer_id"] == issuer]
            fraction = sum(p["fund_fraction"] for p in rows)
            several = sum(p["rows"] for p in rows) > 1
            period = {"type": "AS_OF", "date": fund["holdings_date"]}
            row_ids, row_terms = [], []
            if several:  # share classes, or one company on several rows: each reported row is its own record
                reported = [entry for p in rows for entry in p["reported_rows"]]
                for index, (what, row_fraction) in enumerate(reported, start=1):
                    row_ids.append(self.ev.add(
                        f"ev-cwrow-{fund_id}-{issuer}-{index}", "FACT", "fund_constituent_weight", row_fraction, "ISSUER", issuer, via=fund_id,
                        period=period, sources=[fund["source_id"]], assumptions=[f"One reported row of the fund's holdings file: {what}."],
                    ))
                    row_terms.append(row_fraction)
            constituent = self.ev.add(
                f"ev-cw-{fund_id}-{issuer}", "CALCULATION" if several else "FACT", "fund_constituent_weight", fraction, "ISSUER", issuer, via=fund_id,
                period=period, sources=[fund["source_id"]], derived=row_ids,
                formula=f"sum of the reported rows of this company in the fund: {total(row_terms)} {eq(fraction)}" if several else None,
            )
            derived.append(self.ev.add(
                f"ev-via-{issuer}-{fund_id}-{tag}", "CALCULATION", "issuer_exposure_via_fund", known, "ISSUER", issuer, via=fund_id, state=label,
                derived=[self.weight_ev(fund_id, state), constituent], formula=f"{num(self.position_weight(fund_id, state))} x {num(fraction)} {eq(known)}",
            ))
            terms.append(known)
        lower = exposure["lower"].get(issuer, 0.0)
        lower_id = self.ev.add(
            lower_key, "CALCULATION", "exposure_lower", lower, "ISSUER", issuer, state=label,
            derived=derived or self.scope_weight_evs(state),
            formula=f"{total(terms)} {eq(lower)}" if terms else "no direct holding and no reported fund constituent of this company = 0",
        )
        extra = exposure["possible_extra"]
        upper_id = self.ev.add(
            upper_key, "CALCULATION", "exposure_upper", lower + extra, "ISSUER", issuer, state=label,
            assumptions=[UNATTRIBUTED_NOTE] if extra > 0 else [], derived=[lower_id] + self.unattributed_evs(state),
            formula=f"{num(lower)} + {num(extra)} {eq(lower + extra)}",
        )
        return lower_id, upper_id

    def position_weight(self, instrument_id: str, state: str) -> float:
        for i, weight in held_positions(self.sim[f"{state}_portfolio"]):
            if i == instrument_id:
                return weight
        return 0.0

    # ----- rules

    def threshold_ev(self, rule: dict) -> str:
        if self.a["preview"] and rule["status"] != "CONFIRMED":
            label, assumptions = "ASSUMPTION", ["Draft threshold evaluated in a preview; not confirmed and not stored."]
        elif rule["origin"] == "FICTIONAL_SCENARIO":
            label, assumptions = "FICTIONAL_SCENARIO", []
        else:
            label, assumptions = "FACT", ["Threshold stated and confirmed by the user."]
        return self.ev.add(f"ev-thr-{rule['rule_id']}", label, "rule_threshold", rule["threshold"], "RULE", rule["rule_id"], assumptions=assumptions)

    def measured_evs(self, rule: dict, state: str) -> list[str]:
        """Evidence ids of [lower, upper] measured by the rule on one state ([] when not computable)."""
        result = self.a["results"][rule["rule_id"]][state]
        bounds = result["bounds"]
        if bounds is None:
            return []
        kind = R.rule_kind(rule)
        tag, label = STATE_TAG[state], STATE_LABEL[state]
        rule_id = rule["rule_id"]
        if kind == "SCENARIO":
            return [self.loss_ev(state)]
        if kind == "ONE_ISSUER":
            return list(self.issuer_evs(R.rule_issuer(rule), state))
        if kind == "ANY_ISSUER" and bounds["top_issuer"] is not None:
            return list(self.issuer_evs(bounds["top_issuer"], state))
        exposure = self.exposure[state]
        lower, upper, extra = bounds["lower"], bounds["upper"], exposure["possible_extra"]
        if kind == "ANY_ISSUER":
            lower_id = self.ev.add(
                f"ev-rule-{rule_id}-lo-{tag}", "CALCULATION", "exposure_lower", lower, "RULE", rule_id, state=label,
                derived=self.scope_weight_evs(state), formula="no company exposure is known in this portfolio state = 0",
            )
        else:
            terms, derived, sources = [], [], []
            for part in bounds["parts"]:
                derived.append(self.weight_ev(part["position_id"], state))
                if part["kind"] == "FUND":
                    sources.append(self.fund_info[part["position_id"]]["source_id"])
                    if kind == "SECTOR":  # the fraction multiplied below is itself a record of the calculation path
                        derived.append(self.sector_fraction_ev(rule, part["position_id"], part["fund_fraction"]))
                    terms.append(f"{num(self.position_weight(part['position_id'], state))} x {num(part['fund_fraction'])} (via {part['position_id']})")
                else:
                    terms.append(f"{num(part['known'])} ({part['position_id']} held directly)")
            what = {
                "NAMED": "exposure to the named companies",
                "SECTOR": "exposure carrying exactly this sector label",
                "CONTROVERSY": "exposure to companies with a matching registry record",
            }[kind]
            lower_id = self.ev.add(
                f"ev-rule-{rule_id}-lo-{tag}", "CALCULATION", "exposure_lower", lower, "RULE", rule_id, state=label,
                derived=derived or self.scope_weight_evs(state), sources=sources,
                formula=(f"{what}: " + " + ".join(terms) + f" {eq(lower)}") if terms else f"{what}: none known = 0",
            )
        if kind == "CONTROVERSY":
            in_scope = [w for i, w in held_positions(self.sim[f"{state}_portfolio"]) if self.registry[i]["equity_scope"]]
            upper_id = self.ev.add(
                f"ev-rule-{rule_id}-up-{tag}", "CALCULATION", "exposure_upper", upper, "RULE", rule_id, state=label,
                assumptions=["A company without a matching registry record is not assessed, so all in-scope equity weight could be concerned."],
                derived=self.scope_weight_evs(state), formula=f"all in-scope equity weight: {total(in_scope)} {eq(upper)}",
            )
        elif kind == "SECTOR":
            unclassified = exposure["unclassified_weight"]
            upper_id = self.ev.add(
                f"ev-rule-{rule_id}-up-{tag}", "CALCULATION", "exposure_upper", upper, "RULE", rule_id, state=label,
                assumptions=[UNATTRIBUTED_NOTE, "A holding without a sector label counts toward the upper bound only."],
                derived=[lower_id] + self.unattributed_evs(state) + (self.scope_weight_evs(state) + self.unlabelled_evs(state) if unclassified > 0 else []),
                formula=f"{num(lower)} + {num(extra)} (not reported by the funds) + {num(unclassified)} (reported without a sector label) {eq(upper)}",
            )
        else:
            upper_id = self.ev.add(
                f"ev-rule-{rule_id}-up-{tag}", "CALCULATION", "exposure_upper", upper, "RULE", rule_id, state=label,
                assumptions=[UNATTRIBUTED_NOTE] if extra > 0 else [], derived=[lower_id] + self.unattributed_evs(state),
                formula=f"{num(lower)} + {num(extra)} {eq(upper)}",
            )
        return [lower_id, upper_id]

    def sector_fraction_ev(self, rule: dict, fund_id: str, fraction: float) -> str:
        """The share of one fund that its holdings file labels with the rule's sector."""
        fund, sector = self.fund_info[fund_id], rule["parameters"]["definition"]["sector"]
        return self.ev.add(
            f"ev-secw-{fund_id}-{rule['rule_id']}", "CALCULATION", "fund_constituent_weight", fraction, "FUND", fund_id,
            period={"type": "AS_OF", "date": fund["holdings_date"]}, sources=[fund["source_id"]],
            assumptions=[f"Rows of the fund's holdings file labelled exactly '{sector}'. " + SECTOR_LABEL_NOTE],
            formula=f"sum of the reported weights of the rows labelled '{sector}' {eq(fraction)}",
        )

    def unlabelled_evs(self, state: str) -> list[str]:
        """A null sector_label record for each fund whose holdings file reports no sector label on any row."""
        ids = []
        for fund in self.exposure[state]["funds"]:
            if fund["status"] == "MISSING" or fund["coverage_fraction"] <= 0 or fund["sector_labelled_fraction"] > 0:
                continue
            fund_id = fund["fund_id"]
            ids.append(self.ev.add(
                f"ev-sector-{fund_id}-none", "FACT" if fund["source_id"] else "ASSUMPTION", "sector_label", None, "FUND", fund_id, unit="text",
                period={"type": "AS_OF", "date": fund["holdings_date"]}, sources=[fund["source_id"]],
                assumptions=[
                    f"No constituent row of the {fund_id} holdings file carries a sector label. For a sector rule a missing label counts "
                    "as unknown: it adds to the upper bound only and is never read as outside the sector."
                ],
            ))
        return ids

    def gap_ev(self, rule: dict, state: str) -> Optional[str]:
        result = self.a["results"][rule["rule_id"]][state]
        if result["gap"] is None:
            return None
        measured, limit, status = result["measured"], rule["threshold"], result["status"]
        if rule["rule_type"] == "min_issuer_exposure":
            used = measured["upper"] if status == "FAIL" else measured["lower"]
            formula = f"{num(limit)} - {num(used)} {eq(result['gap'])}"
        else:
            used = measured["lower"] if status == "FAIL" else measured["upper"]
            formula = f"{num(used)} - {num(limit)} {eq(result['gap'])}"
        key = f"ev-gap-{rule['rule_id']}" + ("-start" if state == "starting" else "")
        return self.ev.add(
            key, "CALCULATION", "gap_to_limit", result["gap"], "RULE", rule["rule_id"], state=STATE_LABEL[state],
            assumptions=["Positive = size of the breach; zero or negative = headroom."],
            derived=self.measured_evs(rule, state) + [self.threshold_ev(rule)], formula=formula,
        )

    def subject_evs(self, rule: dict, state: str) -> list[str]:
        ids = []
        result = self.a["results"][rule["rule_id"]][state]
        kind = R.rule_kind(rule)
        for subject in result["breaching_subjects"]:
            issuer = subject["subject_id"]
            ids.extend(self.issuer_evs(issuer, state))
            if kind == "SECTOR":
                label = rule["parameters"]["definition"]["sector"]
                for path in self.exposure[state]["paths"]:
                    if path["issuer_id"] == issuer and path["sector"] == label:
                        fund = self.fund_info.get(path["position_id"]) if path["kind"] == "FUND" else None
                        ids.append(self.ev.add(
                            f"ev-sector-{path['position_id']}-{issuer}", "FACT" if path["sector_source"] else "ASSUMPTION", "sector_label", label, "ISSUER", issuer, unit="text",
                            via=path["position_id"] if fund else None,
                            period={"type": "AS_OF", "date": fund["holdings_date"]} if fund else None,
                            sources=[path["sector_source"]],
                            assumptions=[SECTOR_LABEL_NOTE],
                        ))
            if kind == "CONTROVERSY":
                for record in self.a["flagged"][rule["rule_id"]].get(issuer, []):
                    ids.append(self.ev.add(
                        # SEMANTICS section 13: the value is the registry record_id, the period the event date. What the
                        # registry says about the event is description, kept apart from the value.
                        f"ev-record-{record['record_id']}", "FACT", "controversy_record", record["record_id"],
                        "ISSUER", issuer, unit="text", period={"type": "AS_OF", "date": record["event_date"]}, sources=record["source_ids"],
                        assumptions=[
                            f"Registry record {record['record_id']}, as the registry describes it: {record['nature']} - {record['summary']}",
                            record["coverage_note"],
                            CONTROVERSY_RECORD_NOTE,
                        ],
                    ))
        return ids

    def boundary_evs(self, rule: dict, limiting: Optional[dict]) -> list[str]:
        """Every record the closed-form boundary of one rule is computed from (SEMANTICS section 11).

        The boundary starts from the STARTING portfolio: the limit, the value
        measured before the purchase (with the look-through paths and the
        unattributed fund weight behind it) and what one unit of the purchased
        instrument adds to it.
        """
        ids = [self.threshold_ev(rule)]
        kind = R.rule_kind(rule)
        if kind == "SCENARIO":
            return ids + [self.scenario_evs("starting")[0], self.return_ev(self.requested)]
        issuer = None
        if kind == "ONE_ISSUER":
            issuer = R.rule_issuer(rule)
        elif kind == "ANY_ISSUER" and limiting is not None:
            issuer = limiting["issuer"]
        if issuer is not None:
            lower_id, upper_id = self.issuer_evs(issuer, "starting")
            paths = [i for i in self.ev.record(lower_id)["derived_from"]
                     if self.ev.record(i)["metric_id"] in ("issuer_direct_exposure", "issuer_exposure_via_fund")]
            ids += paths + [lower_id, upper_id]
        else:
            ids += self.measured_evs(rule, "starting")
        if kind != "CONTROVERSY":
            ids += self.unattributed_evs("starting")
        requested = self.registry[self.requested]
        if requested["is_fund"] and requested["equity_scope"] and self.requested in self.fund_info:
            ids.append(self.coverage_ev(self.requested))  # buying a fund: its reported weights set the slope
            if issuer is not None:
                self.issuer_evs(issuer, "proposed")
                key = f"ev-cw-{self.requested}-{issuer}"
                if self.ev.has(key):
                    ids.append(self.ev.id(key))
        return ids

    # ----- scenario

    def _market_fact(self, key: str, metric: str, value: float, kind: str, subject: str, day: str, unit: str, source_key: str, currency: Optional[str] = None) -> str:
        source = self.sources.get(source_key)
        return self.ev.add(
            key, "FACT" if source else "ASSUMPTION", metric, value, kind, subject, unit=unit, currency=currency,
            period={"type": "AS_OF", "date": day}, sources=[source] if source else [], assumptions=[] if source else [UNSOURCED_MARKET_DATA],
        )

    def return_ev(self, instrument_id: str) -> Optional[str]:
        replay, scenario = self.a["replay"], self.a["scenario"]
        history = replay["histories"].get(instrument_id)
        if history is None and instrument_id == self.requested:
            history = replay["target"]
        if history is None:
            return None
        key = f"ev-ret-{instrument_id}"
        if self.ev.has(key):
            return self.ev.id(key)
        derived, sides = [], {}
        for side, day in (("base", scenario["base_date"]), ("end", scenario["end_date"])):
            seen = history[f"_{side}"]
            derived.append(self._market_fact(f"ev-px-{instrument_id}-{side}", "price_adj_close", seen["price"], "INSTRUMENT", instrument_id, seen["price_date"], "price", "prices", history["currency"]))
            derived.append(self.ev.add(
                f"ev-pxage-{instrument_id}-{side}", "CALCULATION", "price_age_days", seen["price_age_days"], "INSTRUMENT", instrument_id, unit="days",
                period={"type": "AS_OF", "date": day}, derived=[derived[-1]], formula=f"days from {seen['price_date']} to {day} = {seen['price_age_days']}",
            ))
            text = num(seen["price"])
            if seen["fx"] is not None:
                rate = self._market_fact(f"ev-fx-{seen['fx_date']}", "fx_usdcad", seen["fx"], "FX", "USDCAD", seen["fx_date"], "fx_rate", "fx_usdcad")
                derived.append(rate)
                derived.append(self.ev.add(
                    f"ev-fxage-{seen['fx_date']}-{side}", "CALCULATION", "fx_rate_age_days", seen["fx_age_days"], "FX", "USDCAD", unit="days",
                    period={"type": "AS_OF", "date": day}, derived=[rate], formula=f"days from {seen['fx_date']} to {day} = {seen['fx_age_days']}",
                ))
                text = f"({num(seen['price'])} x {num(seen['fx'])})"
            sides[side] = text
        return self.ev.add(
            key, "CALCULATION", "scenario_instrument_return", history["return_cad"], "INSTRUMENT", instrument_id,
            period={"type": "RANGE", "start_date": scenario["base_date"], "end_date": scenario["end_date"]},
            assumptions=["Adjusted close; USD prices converted to CAD with the latest Bank of Canada rate on or before each date."],
            derived=derived, formula=f"{sides['end']} / {sides['base']} - 1 {eq(history['return_cad'])}",
        )

    def scenario_evs(self, state: str) -> tuple[Optional[str], Optional[str]]:
        scenario = self.a["scenario"]
        measures = scenario[state] if scenario else None
        if measures is None:
            return None, None
        tag, label = STATE_TAG[state], STATE_LABEL[state]
        period = {"type": "RANGE", "start_date": scenario["base_date"], "end_date": scenario["end_date"]}
        positions = held_positions(self.sim[f"{state}_portfolio"])
        histories = self.a["replay"]["histories"]
        terms = [f"{num(w)} x {num(histories[i]['return_cad'])}" for i, w in positions]
        cash = self.sim[f"{state}_portfolio"]["cash_weight"]
        weights = [self.weight_ev(i, state) for i, _ in positions] + [self.cash_ev(state)]
        terminal = self.ev.add(
            f"ev-scn-ret-{tag}", "CALCULATION", "scenario_terminal_return", measures["scenario_terminal_return"], "PORTFOLIO", self.portfolio_id,
            state=label, period=period, assumptions=scenario["assumptions"],
            derived=weights + [self.return_ev(i) for i, _ in positions],
            formula=" + ".join(terms + [f"{num(cash)} x 0 (cash)"]) + f" {eq(measures['scenario_terminal_return'])}",
        )
        trough = self.a["replay"]["states"][state]["_trough_value"]
        when = f" on {measures['max_drawdown_date']}" if measures["max_drawdown_date"] else ""
        drawdown = self.ev.add(
            f"ev-scn-dd-{tag}", "CALCULATION", "scenario_max_drawdown", measures["scenario_max_drawdown"], "PORTFOLIO", self.portfolio_id,
            state=label, period=period, assumptions=["Context only: drawdown is not a rule."] + list(scenario["assumptions"]),
            derived=weights, sources=[self.sources.get("prices"), self.sources.get("fx_usdcad")],
            formula=(
                f"lowest portfolio value relative to its running maximum (which starts at 1): value {num(trough)}{when}, "
                f"drawdown {num(measures['scenario_max_drawdown'])}"
            ),
        )
        return terminal, drawdown

    def loss_ev(self, state: str) -> str:
        scenario = self.a["scenario"]
        terminal, _ = self.scenario_evs(state)
        value = scenario[state]["scenario_terminal_return"]
        return self.ev.add(
            f"ev-scn-loss-{STATE_TAG[state]}", "CALCULATION", "scenario_loss", 0.0 - value, "PORTFOLIO", self.portfolio_id, state=STATE_LABEL[state],
            period={"type": "RANGE", "start_date": scenario["base_date"], "end_date": scenario["end_date"]},
            derived=[terminal], formula=f"0 - {num(value)} {eq(0.0 - value)}",
        )

    # ----- text

    def subject_words(self, rule: dict, state: str) -> str:
        kind = R.rule_kind(rule)
        if kind == "ANY_ISSUER":
            top = self.a["results"][rule["rule_id"]][state]["bounds"]["top_issuer"]
            return f"the largest single-company exposure ({self.issuer_name(top)})" if top else "the largest single-company exposure"
        if kind == "ONE_ISSUER":
            return f"total exposure to {self.issuer_name(R.rule_issuer(rule))}"
        if kind == "NAMED":
            return "total exposure to the named companies (" + ", ".join(self.issuer_name(i) for i in rule["parameters"]["definition"]["issuer_ids"]) + ")"
        if kind == "SECTOR":
            return f"exposure to holdings labelled '{rule['parameters']['definition']['sector']}'"
        if kind == "CONTROVERSY":
            return "exposure to companies with a matching controversy-registry record"
        return "the terminal loss of the allocation replayed through " + self.a["scenario"]["base_date"] + " to " + self.a["scenario"]["end_date"]

    def reason(self, rule: dict, state: str, causes: list) -> str:
        result = self.a["results"][rule["rule_id"]][state]
        minimum = rule["rule_type"] == "min_issuer_exposure"
        limit_words = f"the {'minimum' if minimum else 'budget' if rule['rule_type'] == 'scenario_loss_budget' else 'limit'} of {pct(rule['threshold'])}"
        when = STATE_WORDS[state].capitalize()
        prefix = "PREVIEW (draft rules, nothing stored): " if self.a["preview"] else ""
        if result["measured"] is None:
            missing = ", ".join(self.a["scenario"]["missing_instruments"])
            return (
                f"{prefix}{when}, {self.subject_words(rule, state)} cannot be computed: no usable price history for {missing} "
                f"over the scenario period. No proxy is substituted, so {limit_words} is neither shown respected nor breached."
            )
        measured = span(result["measured"])
        what = self.subject_words(rule, state)
        if result["status"] == "PASS":
            return f"{prefix}{when}, {what} is {measured}, within {limit_words}."
        if result["status"] == "FAIL":
            side = "below" if minimum else "above"
            return f"{prefix}{when}, {what} is {measured}, at least {points(abs(result['gap']))} percentage points {side} {limit_words}."
        why = "; ".join(UNKNOWN_CAUSE_TEXT[c] for c in causes)
        return f"{prefix}{when}, {what} is {measured}: it can be neither shown to respect nor shown to breach {limit_words} ({why})."


def _not_evaluated_reason(rule: dict, preview: bool) -> str:
    if rule["status"] == "SUPERSEDED":
        by = rule.get("superseded_by_rule_id")
        return f"Superseded{f' by rule {by}' if by else ''} in this policy version; kept for the record and not evaluated."
    if rule["threshold"] is None:
        return "No numeric threshold has been supplied by the user; a rule without a number is never evaluated."
    if rule["status"] == "PROPOSED" and not preview:
        return "Proposed but not confirmed by the user; only confirmed rules are evaluated."
    return "Not evaluated: only confirmed rules with a numeric threshold are evaluated."


def _invalid_result(analysis: dict, portfolio: Any, policy: Optional[dict], request: dict, execution: dict) -> dict:
    def text(source: Any, key: str, default: Any) -> Any:
        value = source.get(key) if isinstance(source, dict) else None
        return value if isinstance(value, str) and value else default

    preview = analysis.get("preview", False)
    policy_id = None if preview else text(policy, "policy_id", None)
    version = policy.get("version") if isinstance(policy, dict) and not preview else None
    result = {
        "schema_version": SCHEMA_VERSION,
        "persona_id": text(portfolio, "persona_id", text(policy, "persona_id", "unknown")),
        "portfolio_id": text(portfolio, "portfolio_id", "unknown"),
        "policy_id": policy_id,
        "policy_version": version if isinstance(version, int) and not isinstance(version, bool) and version >= 1 else None,
        "preview": preview,
        "calculation_version": CALCULATION_VERSION,
        "valuation_date": text(portfolio, "valuation_date", DEFAULT_VALUATION_DATE),
        "purchase_request": request,
        "execution": execution,
        "feasibility": None,
        "policy_consistency": {"status": "NOT_ASSESSED", "conflicts": []},
        "rule_results": [],
        "rules_not_evaluated": [],
        "starting_portfolio_findings": [],
        "data_coverage": [],
        "scenario": None,
        "goal_context": [],
        "max_compliant": None,
        "exposure": None,
        "evidence": [],
        "disclosures": list(DISCLOSURES),
    }
    result["summary"] = derive_summary(result)
    return result


def check_rules(
    portfolio: dict,
    policy: Optional[dict],
    purchase_request: dict,
    instruments: Any,
    holdings: Any,
    market_data: Any,
    controversies: Any,
    *,
    draft_rules: Optional[list] = None,
    data_sources: Optional[dict] = None,
    include_max_compliant: bool = True,
) -> dict:
    """Evaluate one purchase request and return a full ``check_result`` document.

    ``policy`` is the stored policy version; with ``draft_rules`` the result is a
    preview (the policy then only supplies the objectives and may be None).
    A purchase request that does not match its schema raises ``ContractError``
    and a call with neither a policy nor draft rules raises ``ValueError``:
    no valid result can describe either. Any other failure is returned as
    ``execution.status`` ``ERROR``. ``data_sources`` optionally names the source ids of the market data
    (``{"prices": ..., "fx_usdcad": ...}``) so price and FX evidence can be
    labelled FACT. ``include_max_compliant=False`` is used by the boundary
    re-run: the section is then WITHHELD with a reason saying so.
    """
    refuse_unusable_request(purchase_request)
    validate_purchase_request(purchase_request)
    if policy is None and draft_rules is None:
        raise ValueError("check_rules needs a policy, or draft_rules for a preview")
    analysis: dict = {"preview": draft_rules is not None}
    try:
        if include_max_compliant:  # the boundary re-run reuses data this call has already checked
            problems = data_problems(instruments, holdings, market_data, controversies)
            if problems:
                execution = {"status": "ERROR", "code": "ENGINE_ERROR",
                             "message": "The check was not run because the data cannot be trusted: " + "; ".join(problems) + ". Nothing was calculated."}
                return _invalid_result(analysis, portfolio, policy, purchase_request, execution)
        analysis = analyse(portfolio, policy, purchase_request, instruments, holdings, market_data, controversies, draft_rules)
        if not analysis["ok"]:
            return _invalid_result(analysis, portfolio, policy, purchase_request, analysis["sim"]["execution"])
        result = _build(analysis, portfolio, policy, purchase_request, instruments, holdings, market_data, controversies,
                        draft_rules, data_sources, include_max_compliant)
        if non_finite_paths(result, "result", 1):  # last line of defence: no NaN or infinity ever leaves the engine
            raise ArithmeticError("a computed value is not finite")
        return result
    except ContractError:
        raise  # an invalid purchase request: documented above, no result can carry it
    except Exception:  # SEMANTICS section 4: an unexpected failure is reported, never raised to the caller
        # The message is fixed text: exception text can hold internal detail and is not for the user.
        execution = {"status": "ERROR", "code": "ENGINE_ERROR",
                     "message": "The check could not be completed because of an internal error. Nothing was calculated."}
        return _invalid_result({"preview": draft_rules is not None}, portfolio, policy, purchase_request, execution)


def _build(analysis, portfolio, policy, request, instruments, holdings, market_data, controversies, draft_rules, data_sources, include_max) -> dict:
    doc = _Document(analysis, portfolio, policy, request, data_sources)
    ev, sim, exposure = doc.ev, analysis["sim"], analysis["exposure"]
    preview, evaluated, results = analysis["preview"], analysis["evaluated"], analysis["results"]
    evaluated_ids = {rule["rule_id"] for rule in evaluated}

    # data coverage (also creates the fund evidence in portfolio order)
    data_coverage = [dict(fund) for fund in exposure["proposed"]["funds"]]
    for state in STATES:
        doc.unattributed_evs(state)

    # rule results and starting-portfolio findings
    rule_results, findings = [], []
    for rule in evaluated:
        rule_id = rule["rule_id"]
        result = results[rule_id]
        proposed, starting = result["proposed"], result["starting"]
        scenario_rule = rule["rule_type"] == "scenario_loss_budget"
        evidence_ids = doc.measured_evs(rule, "proposed") + [doc.threshold_ev(rule)]
        gap_id = doc.gap_ev(rule, "proposed")
        if gap_id:
            evidence_ids.append(gap_id)
        if not scenario_rule:
            evidence_ids += [i for i in doc.unattributed_evs("proposed")]
            evidence_ids += doc.subject_evs(rule, "proposed")
            if "UNCLASSIFIED_SECTOR" in result["unknown_causes"]:
                evidence_ids += doc.unlabelled_evs("proposed")
        evidence_ids += doc.measured_evs(rule, "starting")
        rule_results.append({
            "rule_id": rule_id,
            "rule_type": rule["rule_type"],
            "status": proposed["status"],
            "measured": proposed["measured"],
            "limit": rule["threshold"],
            "gap": proposed["gap"],
            "breaching_subjects": proposed["breaching_subjects"],
            "out_of_scope": [] if scenario_rule else [dict(entry) for entry in exposure["proposed"]["out_of_scope"]],
            "unknown_causes": [cause for cause in UNKNOWN_CAUSES if cause in result["unknown_causes"]],
            "starting": {"status": starting["status"], "measured": starting["measured"]},
            "evidence_ids": list(dict.fromkeys(evidence_ids)),
            "reason": doc.reason(rule, "proposed", result["unknown_causes"]),
        })
        if starting["status"] == "FAIL":
            effect = {
                "lower_change": proposed["measured"]["lower"] - starting["measured"]["lower"],
                "upper_change": proposed["measured"]["upper"] - starting["measured"]["upper"],
            }
            finding_ids = doc.measured_evs(rule, "starting") + [doc.threshold_ev(rule), doc.gap_ev(rule, "starting")] + doc.subject_evs(rule, "starting")
            findings.append({
                "rule_id": rule_id,
                "status": "FAIL",
                "measured": starting["measured"],
                "limit": rule["threshold"],
                "gap": starting["gap"],
                "breaching_subjects": starting["breaching_subjects"],
                "purchase_effect": effect,
                "evidence_ids": list(dict.fromkeys(finding_ids)),
                "reason": (
                    "Already breached before any purchase: " + doc.reason(rule, "starting", []) +
                    f" The purchase itself changes the measured bounds by {points(effect['lower_change'], signed=True)} (lower) and "
                    f"{points(effect['upper_change'], signed=True)} (upper) percentage points."
                ),
            })

    rules_not_evaluated = [
        {"rule_id": rule["rule_id"], "status": rule["status"], "reason": _not_evaluated_reason(rule, preview)}
        for rule in analysis["rules"] if rule["rule_id"] not in evaluated_ids
    ]

    # scenario
    scenario = analysis["scenario"]
    if scenario is not None:
        scenario = dict(scenario)
        ids = []
        for state in STATES:
            ids.extend(i for i in doc.scenario_evs(state) if i)
        for row in scenario["instrument_returns"]:
            ids.append(doc.return_ev(row["instrument_id"]))
        target = doc.return_ev(doc.requested)
        if target:
            ids.append(target)
        scenario["evidence_ids"] = list(dict.fromkeys(ids))

    # exposure chart rows
    chosen: list[str] = []
    requested = doc.registry[doc.requested]
    if requested["equity_scope"] and not requested["is_fund"]:
        chosen.append(requested["issuer_id"])
    for rule in evaluated:
        chosen.extend(R.named_issuers(rule))
    for rule in evaluated:
        for state in ("proposed", "starting"):
            chosen.extend(subject["subject_id"] for subject in results[rule["rule_id"]][state]["breaching_subjects"])
    proposed_lower = exposure["proposed"]["lower"]
    chosen.extend(sorted(proposed_lower, key=lambda issuer: (-proposed_lower[issuer], issuer)))
    chosen = sorted(list(dict.fromkeys(chosen))[:EXPOSURE_TOP_N], key=lambda issuer: (-proposed_lower.get(issuer, 0.0), issuer))
    issuers = []
    for issuer in chosen:
        entry = {"issuer_id": issuer, "name": doc.issuer_name(issuer)}
        for state in STATES:
            lower = exposure[state]["lower"].get(issuer, 0.0)
            entry[state] = {
                "direct": R.as_fraction(exposure[state]["direct"].get(issuer, 0.0)),
                "indirect_by_fund": [{"fund_id": f, "known": k} for f, k in exposure[state]["via_fund"].get(issuer, {}).items() if k > 0],
                "lower": R.as_fraction(lower),
                "upper": R.as_fraction(lower + exposure[state]["possible_extra"]),
            }
            doc.issuer_evs(issuer, state)
        issuers.append(entry)
    exposure_section = {
        "possible_extra": {state: R.as_fraction(exposure[state]["possible_extra"]) for state in STATES},
        "issuers": issuers,
        "selection_note": EXPOSURE_SELECTION_NOTE,
    }

    # goal context: qualitative, never a status
    goal_context = []
    objectives = analysis["objectives"]
    for objective in objectives:
        linked = [rule for rule in evaluated if rule["objective_id"] == objective["objective_id"]]
        if linked:
            listed = ", ".join(f"{rule['rule_id']} ({results[rule['rule_id']]['proposed']['status']})" for rule in linked)
            ids = []
            for rule in linked:
                ids.append(doc.gap_ev(rule, "proposed") or doc.threshold_ev(rule))
            goal_context.append({
                "objective_id": objective["objective_id"],
                "context_type": "LINKED_RULE_RESULTS",
                "text": (
                    f"{len(linked)} evaluated rule{'s are' if len(linked) > 1 else ' is'} linked to this objective as context: {listed}. "
                    "The objective itself is qualitative and has no PASS or FAIL."
                ),
                "evidence_ids": list(dict.fromkeys(ids)),
            })
        else:
            goal_context.append({
                "objective_id": objective["objective_id"],
                "context_type": "NOT_QUANTIFIED",
                "text": "No evaluated rule is linked to this objective. It is kept in the investor's own words and is not quantified: it has no PASS or FAIL.",
                "evidence_ids": [],
            })
    if objectives:
        anchor = next((o for o in objectives if o["kind"] == "goal"), objectives[0])["objective_id"]
        if exposure["proposed"]["in_scope_weight"] > 0:
            ids, words = [], {}
            for state in STATES:
                lower_by_issuer = exposure[state]["lower"]
                extra = exposure[state]["possible_extra"]
                top = min(lower_by_issuer, key=lambda issuer: (-lower_by_issuer[issuer], issuer)) if lower_by_issuer else None
                if top is None:
                    words[state] = f"no known company exposure {STATE_WORDS[state]}" + (f" (up to {pct(extra)} is not attributed)" if extra > 0 else "")
                    ids.extend(doc.unattributed_evs(state))
                else:
                    words[state] = f"{span({'lower': lower_by_issuer[top], 'upper': lower_by_issuer[top] + extra})} ({doc.issuer_name(top)}) {STATE_WORDS[state]}"
                    ids.extend(doc.issuer_evs(top, state))
            goal_context.append({
                "objective_id": anchor,
                "context_type": "CONCENTRATION",
                "text": f"Largest single-company exposure: {words['starting']}, {words['proposed']}. Context only; it is not a rule result.",
                "evidence_ids": list(dict.fromkeys(ids)),
            })
        if scenario is not None and scenario["status"] == "COMPUTED":
            goal_context.append({
                "objective_id": anchor,
                "context_type": "SCENARIO_DRAWDOWN",
                "text": (
                    f"Deepest fall inside the historical replay ({scenario['base_date']} to {scenario['end_date']}): "
                    f"{pct(-scenario['starting']['scenario_max_drawdown'])} before the purchase, {pct(-scenario['proposed']['scenario_max_drawdown'])} after it. "
                    "Context only; drawdown is not one of the rules and this is not a forecast."
                ),
                "evidence_ids": [doc.scenario_evs("starting")[1], doc.scenario_evs("proposed")[1]],
            })

    # maximum compliant weight
    conflicts = analysis["conflicts"]
    if include_max:
        from .boundary import solve_max_compliant
        max_compliant, detail = solve_max_compliant(
            analysis, portfolio, policy, request, instruments, holdings, market_data, controversies, draft_rules, data_sources)
        if max_compliant["status"] == "SUPPORTED":
            start_id = doc.weight_ev(doc.requested, "starting")
            inputs = []
            for rule in evaluated:  # binding and non-binding constraints alike
                inputs += doc.boundary_evs(rule, detail["rules"][rule["rule_id"]]["limiting"])
            inputs += ["ev-cash-start", start_id]
            final_id = ev.add(
                "ev-max-final", "CALCULATION", "max_compliant_final_weight", max_compliant["final_direct_weight"], "INSTRUMENT", doc.requested, state="PROPOSED",
                assumptions=["Closed form: every bound is linear in the target weight. Verified by re-running the same checks at this weight."],
                derived=inputs, formula=detail["formula"],
            )
            added_id = ev.add(
                "ev-max-added", "CALCULATION", "max_compliant_additional_purchase", max_compliant["additional_purchase"], "INSTRUMENT", doc.requested, state="PROPOSED",
                derived=[final_id, start_id] + inputs,
                formula=f"{num(max_compliant['final_direct_weight'])} - {num(sim['feasibility']['starting_direct_weight'])} {eq(max_compliant['additional_purchase'])}",
            )
            max_compliant["evidence_ids"] = [final_id, added_id]
        elif max_compliant["status"] == "NO_FEASIBLE_PURCHASE":
            binding = max_compliant["binding_constraint"]
            if binding["type"] == "RULE":
                # What proves it: the bound measured before any purchase that is already on the wrong side of the limit
                # (the lower bound for a maximum, the upper bound for a minimum), and the limit.
                rule = next(r for r in evaluated if r["rule_id"] == binding["rule_id"])
                measured = doc.measured_evs(rule, "starting")
                proof = measured[-1:] if rule["rule_type"] == "min_issuer_exposure" else measured[:1]
                max_compliant["evidence_ids"] = proof + [doc.threshold_ev(rule)]
            else:
                max_compliant["evidence_ids"] = ["ev-cash-start"]
    else:
        max_compliant = {
            "status": "WITHHELD", "final_direct_weight": None, "additional_purchase": None, "binding_constraint": None,
            "verified_by_rerun": False, "reason": "Not computed in this run (rule evaluation only).", "evidence_ids": [],
        }

    result = {
        "schema_version": SCHEMA_VERSION,
        "persona_id": portfolio["persona_id"],
        "portfolio_id": portfolio["portfolio_id"],
        "policy_id": None if preview else policy["policy_id"],
        "policy_version": None if preview else policy["version"],
        "preview": preview,
        "calculation_version": CALCULATION_VERSION,
        "valuation_date": portfolio["valuation_date"],
        "purchase_request": request,
        "execution": sim["execution"],
        "feasibility": sim["feasibility"],
        "policy_consistency": {"status": "PROVEN_CONFLICT" if conflicts else "CONSISTENT", "conflicts": conflicts},
        "rule_results": rule_results,
        "rules_not_evaluated": rules_not_evaluated,
        "starting_portfolio_findings": findings,
        "data_coverage": data_coverage,
        "scenario": scenario,
        "goal_context": goal_context,
        "max_compliant": max_compliant,
        "exposure": exposure_section,
        "evidence": ev.records,
        "disclosures": list(DISCLOSURES),
    }
    result["summary"] = derive_summary(result)
    return result
