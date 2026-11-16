"""Missing-data scanner for one fund, and bounded retrieval from the approved local sources.

Three things are kept apart, because they do not mean the same:

A. holdings coverage        share of the FUND's weight held in rows that carry a usable weight and identifier
B. classification coverage  share of the FUND's weight whose property (sector; country) is known
C. source confidence        is the evidence dated, traceable to a registered source, and self-consistent

Measurement basis. A row's ``weight_fraction`` is the fraction of the fund printed in the issuer's holdings
file; weights are never rescaled (holdings_snapshot.schema.json, LEAD_DECISIONS D4). So the sum of usable row
weights is a share of the fund, and ``1 - sum`` is the share this snapshot cannot attribute to a constituent.
The number of rows is never used as a share of anything. When the printed weights do not reconcile (they add
up to more than the fund, or disagree with the declared coverage) no percentage is reported at all.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

# The snapshot contract checks ``coverage_fraction == sum(rows)`` within this.
SUM_TOLERANCE = 1e-8
# Issuer files print rounded weights, so all printed lines can add up to slightly more than the fund.
# Beyond this the weights are treated as not reconciling. Disclosed in every result (``calculation_basis``).
TOTAL_TOLERANCE = 0.005

BASIS_ISSUER_FILE = "issuer_holdings_file"
BASIS_NO_FILE = "no_holdings_file"
BASIS_UNRECONCILED = "unreconciled_weights"

STATUS_SUFFICIENT = "sufficient_evidence"
STATUS_PARTIAL = "partial_evidence"
STATUS_INSUFFICIENT = "insufficient_evidence"

EVIDENCE_UNAVAILABLE = "Evidence unavailable — no verified replacement found."
LOCAL_ONLY_LIMITATION = ("Evidence is retrieved from the verified data snapshot only (issuer holdings files, the instrument "
                         "registry and the source registry). No external provider is configured, so nothing was fetched from outside.")


class UnknownFund(Exception):
    """The identifier is not a fund of the snapshot's instrument registry."""


def pct(fraction: float | None) -> float | None:
    """Fraction -> percentage points, rounded so that float noise never shows (``None`` stays ``None``)."""
    return None if fraction is None else round(fraction * 100.0, 6)


def _usable_weight(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0.0 < value <= 1.0


def _text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _days_between(earlier: Any, later: Any) -> int | None:
    try:
        return (date.fromisoformat(later) - date.fromisoformat(earlier)).days
    except (TypeError, ValueError):
        return None


def _issue(code: str, severity: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "detail": detail}


def _source_observation(source_id: Any, sources: dict, subject: str, observed: dict, as_of: Any, verified: bool) -> dict[str, Any]:
    record = sources.get(source_id) if isinstance(source_id, str) else None
    return {
        "source_id": source_id if isinstance(source_id, str) else None,
        "publisher": (record or {}).get("publisher"),
        "title": (record or {}).get("title"),
        "url": (record or {}).get("url"),
        "as_of_date": as_of if _text(as_of) else None,
        "retrieval_date": (record or {}).get("retrieval_date"),
        "subject": subject,
        "observed": observed,
        "verification": "verified" if verified and record is not None else "provisional",
        "in_source_registry": record is not None,
    }


def scan_fund(fund_id: Any, registry: dict, funds: dict, sources: dict, valuation_date: str | None = None) -> dict[str, Any]:
    """Everything the snapshot holds, and does not hold, about one fund. Raises ``UnknownFund``.

    The returned dict is the public result plus ``_calc`` (fractions for ``bounds``; removed by ``public``).
    """
    instrument = registry.get(fund_id) if isinstance(fund_id, str) else None
    if instrument is None or not instrument.get("is_fund"):
        raise UnknownFund(str(fund_id)[:64])
    entry = funds.get(fund_id)
    equity_scope = bool(instrument.get("equity_scope"))
    result: dict[str, Any] = {
        "fund": fund_id,
        "fund_name": instrument.get("name"),
        "asset_class": instrument.get("asset_class"),
        "in_rule_scope": equity_scope,
        "snapshot_date": None,
        "publication_date": None,
        "retrieval_date": None,
        "evidence_age_days": None,
        "coverage_basis": BASIS_NO_FILE,
        "verified_weight_pct": None,
        "unresolved_weight_pct": None,
        "unresolved_breakdown": None,
        "classification_coverage": {
            "sector": {"classified_weight_pct": None, "unclassified_weight_pct": None, "labels": {}},
            "country": {"classified_weight_pct": None, "unclassified_weight_pct": None,
                        "reason": "The holdings data contract carries no country field, so no country share can be measured."},
        },
        "rows": {"reported": 0, "usable": 0, "missing_weight": 0, "invalid_weight": 0, "missing_identifier": 0,
                 "missing_sector": 0, "duplicated": 0},
        "missing_fields": [],
        "data_quality_issues": [],
        "source_confidence": {"level": "unavailable", "dated": False, "traceable": False, "consistent": False,
                              "synthetic_test_data": False, "notes": []},
        "evidence_sources": [],
        "retrieval": None,
        "hypothetical_scenarios": [],
        "limitations": [LOCAL_ONLY_LIMITATION],
        "calculation_basis": None,
        "status": STATUS_INSUFFICIENT,
    }
    missing, issues, limitations = result["missing_fields"], result["data_quality_issues"], result["limitations"]
    missing.append({"field": "country", "scope": "every holding", "rows": None, "weight_pct": None,
                    "effect": "Country exposure cannot be measured for this fund from the snapshot."})

    registry_observation = _source_observation(
        instrument.get("sector_source"), sources, fund_id,
        {"kind": "instrument_registry_entry", "asset_class": instrument.get("asset_class"), "fund_level_label": instrument.get("sector")},
        None, True)
    searched = [{"source": "data snapshot: fund holdings file", "found": entry is not None},
                {"source": "data snapshot: instrument registry", "found": True}]

    if entry is None:
        # No holdings file: nothing is verified, so the whole fund is unresolved (D4: coverage 0, never zero exposure).
        result["unresolved_weight_pct"] = 100.0
        result["calculation_basis"] = "No holdings file is held for this fund. Nothing can be measured; the whole fund is unresolved."
        missing.insert(0, {"field": "holdings", "scope": "whole fund", "rows": None, "weight_pct": 100.0,
                           "effect": "No constituent, weight or classification of this fund is known."})
        if not equity_scope:
            limitations.append("This fund is outside the look-through scope of the investor rules (bond, commodity or other "
                               "non-equity fund), so its constituents are not acquired.")
        related = _related_sources(fund_id, sources)
        searched.append({"source": "data snapshot: source registry", "found": bool(related)})
        result["evidence_sources"] = [registry_observation] + related
        result["retrieval"] = {"searched": searched, "external_retrieval": "not_configured", "message": EVIDENCE_UNAVAILABLE}
        result["_calc"] = {"basis_valid": False, "no_file": True, "verified": 0.0, "unresolved": 1.0, "unclassified": 0.0, "sectors": {}}
        return result

    rows = entry.get("holdings") if isinstance(entry.get("holdings"), list) else []
    counts = result["rows"]
    counts["reported"] = len(rows)
    usable_sum = 0.0          # rows with a usable weight AND an identifier
    unidentified_sum = 0.0    # usable weight, but no issuer / instrument identifier
    printed_sum = 0.0         # every usable weight, identified or not
    unclassified = 0.0
    sectors: dict[str, float] = {}
    seen: dict[str, int] = {}
    for row in rows:
        row = row if isinstance(row, dict) else {}
        weight = row.get("weight_fraction")
        if weight is None:
            counts["missing_weight"] += 1
            continue
        if not _usable_weight(weight):
            counts["invalid_weight"] += 1
            continue
        printed_sum += weight
        key = row.get("instrument_id") if _text(row.get("instrument_id")) else None
        if key is not None:
            seen[key] = seen.get(key, 0) + 1
        if not (_text(row.get("issuer_id")) and _text(row.get("instrument_id"))):
            counts["missing_identifier"] += 1
            unidentified_sum += weight
            continue
        counts["usable"] += 1
        usable_sum += weight
        if _text(row.get("sector")):
            sectors[row["sector"]] = sectors.get(row["sector"], 0.0) + weight
        else:
            counts["missing_sector"] += 1
            unclassified += weight
    counts["duplicated"] = sum(count - 1 for count in seen.values() if count > 1)

    declared = entry.get("coverage_fraction")
    non_constituent = entry.get("non_constituent_weight")
    non_constituent = float(non_constituent) if isinstance(non_constituent, (int, float)) and not isinstance(non_constituent, bool) \
        and math.isfinite(non_constituent) and non_constituent >= 0 else None

    # ---- reconciliation: is there a defensible basis for a percentage?
    reconciled = True
    if printed_sum + (non_constituent or 0.0) > 1.0 + TOTAL_TOLERANCE:
        reconciled = False
        issues.append(_issue("WEIGHTS_EXCEED_FUND", "blocking",
                             f"The printed weights add up to {pct(printed_sum + (non_constituent or 0.0))}% of the fund, more than the fund itself."))
    if not _usable_weight(declared) and declared != 0:
        if not (isinstance(declared, (int, float)) and not isinstance(declared, bool) and math.isfinite(declared) and declared >= 0):
            reconciled = False
            issues.append(_issue("DECLARED_COVERAGE_INVALID", "blocking", "The declared coverage of the holdings file is missing or not a usable number."))
    if reconciled and isinstance(declared, (int, float)) and abs(declared - printed_sum) > SUM_TOLERANCE:
        reconciled = False
        issues.append(_issue("COVERAGE_MISMATCH", "blocking",
                             f"The declared coverage ({pct(declared)}%) differs from the sum of the usable row weights ({pct(printed_sum)}%)."))
    if counts["missing_weight"]:
        reconciled = False
        issues.append(_issue("MISSING_WEIGHTS", "blocking", f"{counts['missing_weight']} holding row(s) carry no weight; their share of the fund is unknown."))
        missing.insert(0, {"field": "weight_fraction", "scope": "holding rows", "rows": counts["missing_weight"], "weight_pct": None,
                           "effect": "The share of the fund held by these rows is unknown, so no coverage percentage is reported."})
    if counts["invalid_weight"]:
        reconciled = False
        issues.append(_issue("INVALID_WEIGHTS", "blocking", f"{counts['invalid_weight']} holding row(s) carry a weight that is not a fraction in (0, 1]."))
    if isinstance(entry.get("n_holdings"), int) and entry["n_holdings"] != len(rows):
        issues.append(_issue("ROW_COUNT_MISMATCH", "warning",
                             f"The file declares {entry['n_holdings']} holdings but {len(rows)} row(s) are present."))
    if counts["duplicated"]:
        issues.append(_issue("DUPLICATED_HOLDINGS", "warning",
                             f"{counts['duplicated']} row(s) repeat an instrument already listed. Their weights are kept as printed, not merged or dropped."))
    if counts["missing_identifier"]:
        issues.append(_issue("MISSING_IDENTIFIERS", "warning",
                             f"{counts['missing_identifier']} row(s) carry a weight but no issuer or instrument identifier; they are not counted as verified."))
        missing.append({"field": "issuer_id / instrument_id", "scope": "holding rows", "rows": counts["missing_identifier"],
                        "weight_pct": pct(unidentified_sum) if reconciled else None,
                        "effect": "These positions cannot be attributed to a company, so they count as unresolved."})

    # ---- dates
    holdings_date = entry.get("holdings_date") if _text(entry.get("holdings_date")) else None
    result["snapshot_date"] = holdings_date
    result["publication_date"] = entry.get("publication_date") if _text(entry.get("publication_date")) else None
    result["retrieval_date"] = entry.get("retrieval_date") if _text(entry.get("retrieval_date")) else None
    if holdings_date is None:
        issues.append(_issue("MISSING_SNAPSHOT_DATE", "warning", "The holdings file carries no 'as of' date."))
        missing.append({"field": "holdings_date", "scope": "holdings file", "rows": None, "weight_pct": None,
                        "effect": "It cannot be said which day these holdings describe."})
    if result["publication_date"] is None:
        missing.append({"field": "publication_date", "scope": "holdings file", "rows": None, "weight_pct": None,
                        "effect": "When the issuer published this file is not recorded."})
    age = _days_between(holdings_date, valuation_date) if holdings_date and valuation_date else None
    result["evidence_age_days"] = age
    if age is not None and age != 0:
        issues.append(_issue("DATE_DIFFERS_FROM_VALUATION", "warning",
                             f"The holdings are as of {holdings_date}; the portfolio is valued on {valuation_date} ({age} day(s) apart). "
                             "They are used together without adjustment."))
    limitations.append("No freshness policy is defined for holdings in this project: the age of the evidence is reported, not judged.")

    # ---- A. holdings coverage, B. classification coverage (only on a reconciled basis)
    calc: dict[str, Any] = {"basis_valid": reconciled, "no_file": False, "verified": 0.0, "unresolved": 1.0, "unclassified": 0.0, "sectors": {}}
    if reconciled:
        unresolved = max(0.0, 1.0 - usable_sum)
        result["coverage_basis"] = BASIS_ISSUER_FILE
        result["verified_weight_pct"] = pct(usable_sum)
        result["unresolved_weight_pct"] = pct(unresolved)
        reported_other = min(non_constituent or 0.0, unresolved) if non_constituent is not None else None
        unattributed = max(0.0, unresolved - (reported_other or 0.0) - unidentified_sum)
        result["unresolved_breakdown"] = {
            "reported_non_constituent_pct": pct(reported_other),
            "rows_without_identifier_pct": pct(unidentified_sum),
            "unattributed_pct": pct(unattributed),
            "note": ("Reported non-constituent lines are cash, derivatives or similar lines printed in the issuer file. The unattributed "
                     "remainder has no stated cause (issuer rounding, unlisted net assets or unreported positions): it is not assumed "
                     "to be missing holdings."),
        }
        result["classification_coverage"]["sector"] = {
            "classified_weight_pct": pct(sum(sectors.values())),
            "unclassified_weight_pct": pct(unclassified),
            "labels": {label: pct(value) for label, value in sorted(sectors.items())},
        }
        result["calculation_basis"] = (
            "Weights are fractions of the fund as printed in the issuer's holdings file and are never rescaled. Verified = sum of the rows "
            "with a usable weight and identifier. Unresolved = 100% - verified. Sector shares are sums of those same weights. "
            f"Printed weights may exceed 100% by at most {pct(TOTAL_TOLERANCE)} percentage points (issuer rounding) before they are refused.")
        calc.update(verified=usable_sum, unresolved=unresolved, unclassified=unclassified, sectors=dict(sectors))
        if unresolved > SUM_TOLERANCE:
            missing.insert(0, {"field": "holdings", "scope": "part of the fund", "rows": None, "weight_pct": pct(unresolved),
                               "effect": "This share of the fund is not attributed to any constituent in the snapshot."})
        if counts["missing_sector"]:
            missing.append({"field": "sector", "scope": "holding rows", "rows": counts["missing_sector"], "weight_pct": pct(unclassified),
                            "effect": "These holdings are known, but their sector is not: for a sector rule they count toward the upper bound only."})
    else:
        result["coverage_basis"] = BASIS_UNRECONCILED
        result["calculation_basis"] = ("The weights in the holdings file do not reconcile, so no coverage or classification percentage is "
                                       "reported for this fund. For portfolio bounds the whole fund is treated as unresolved.")
        if counts["missing_sector"]:
            missing.append({"field": "sector", "scope": "holding rows", "rows": counts["missing_sector"], "weight_pct": None,
                            "effect": "The sector of these holdings is not known."})

    # ---- C. source confidence
    source_id = entry.get("source_id")
    record = sources.get(source_id) if isinstance(source_id, str) else None
    synthetic = record is not None and ("synthetic" in str(record.get("publisher", "")).lower() or source_id == "SYNTHETIC_FIXTURE")
    traceable = record is not None and _text(record.get("sha256"))
    notes = []
    if record is None:
        notes.append("The holdings file names no source that is in the source registry.")
    if synthetic:
        notes.append("The source is synthetic test data: invented numbers, not an issuer disclosure.")
    if not reconciled:
        notes.append("The file is not self-consistent (see data quality issues).")
    confidence = result["source_confidence"]
    confidence.update(dated=holdings_date is not None, traceable=bool(traceable), consistent=reconciled, synthetic_test_data=bool(synthetic), notes=notes)
    confidence["level"] = "verified" if (holdings_date and traceable and reconciled and not synthetic) else "provisional"

    holdings_observation = _source_observation(
        source_id, sources, fund_id,
        {"kind": "fund_holdings_file", "rows": len(rows), "sum_of_usable_weights_pct": pct(printed_sum),
         "declared_coverage_pct": pct(declared) if isinstance(declared, (int, float)) and not isinstance(declared, bool) else None,
         "reported_non_constituent_pct": pct(non_constituent)},
        holdings_date, confidence["level"] == "verified")
    related = [item for item in _related_sources(fund_id, sources) if item["source_id"] != source_id]
    searched.append({"source": "data snapshot: source registry", "found": record is not None or bool(related)})
    result["evidence_sources"] = [holdings_observation, registry_observation] + related
    needs_more = (not reconciled) or calc["unresolved"] > SUM_TOLERANCE or counts["missing_sector"] > 0
    result["retrieval"] = {"searched": searched, "external_retrieval": "not_configured", "message": EVIDENCE_UNAVAILABLE if needs_more else None}

    blocking = any(issue["severity"] == "blocking" for issue in issues)
    if blocking:
        result["status"] = STATUS_INSUFFICIENT
    elif needs_more or counts["missing_identifier"] or holdings_date is None:
        result["status"] = STATUS_PARTIAL
    else:
        result["status"] = STATUS_SUFFICIENT
    result["_calc"] = calc
    return result


def _related_sources(fund_id: str, sources: dict) -> list[dict[str, Any]]:
    """Registered sources whose id names this fund's ticker. Listed for traceability; nothing is parsed out of them here."""
    ticker = fund_id.split(".")[0].lower()
    found = []
    for source_id in sorted(sources):
        tokens = source_id.lower().replace("-", "_").split("_")
        if ticker in tokens:
            found.append(_source_observation(source_id, sources, fund_id, {"kind": "registered_source", "note": "listed in the source registry"},
                                             sources[source_id].get("relevant_date"), True))
    return found[:5]


def public(scan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in scan.items() if not key.startswith("_")}
