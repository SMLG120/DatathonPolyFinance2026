"""validate_* functions for inputs and data files. Standard library only.

Every function starts with ``schema_errors``, which first rejects any NaN or
+/-Infinity anywhere in the document (naming its path), so no check below ever
compares against a non-finite number.

Each function checks the JSON Schema shape first (through ``schema.py``) and
then the semantic rules a schema cannot express (weights that must add up, id
links, hashes). On any problem it raises ``ContractError`` listing every issue
found, each with the path of the offending field.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional

from .constants import ASSET_CLASS_FLAGS, COVERAGE_SUM_TOLERANCE, EPS
from .derive import compute_content_hash
from .schema import schema_errors


class ContractError(ValueError):
    """A payload does not satisfy the contract."""

    def __init__(self, what: str, errors: list[str]):
        self.what = what
        self.errors = list(errors)
        shown = "\n  - ".join(self.errors[:25])
        more = f"\n  ... and {len(self.errors) - 25} more" if len(self.errors) > 25 else ""
        super().__init__(f"{what} is invalid ({len(self.errors)} issue(s)):\n  - {shown}{more}")


def _raise(what: str, errors: list[str]) -> None:
    if errors:
        raise ContractError(what, errors)


def validate_against(schema_ref: str, payload: Any, what: Optional[str] = None) -> None:
    """Shape-only validation against any schema reference, e.g. 'api.schema.json#/$defs/check_request'."""
    _raise(what or schema_ref, schema_errors(payload, schema_ref))


def _duplicates(values: Iterable[Any]) -> list[Any]:
    seen, dup = set(), []
    for value in values:
        if value in seen and value not in dup:
            dup.append(value)
        seen.add(value)
    return dup


# --------------------------------------------------------------------------- portfolio / request

def _weights_add_up(total: float) -> bool:
    """True only for a finite total within EPS of 1. Written so that NaN can never satisfy it."""
    return math.isfinite(total) and abs(total - 1.0) <= EPS


def portfolio_errors(portfolio: Any) -> list[str]:
    errors = schema_errors(portfolio, "portfolio.schema.json")
    if errors:
        return errors
    total = portfolio["cash_weight"] + sum(p["weight"] for p in portfolio["positions"])
    if not _weights_add_up(total):
        errors.append(f"cash_weight + sum(positions.weight) = {total!r}, must equal 1 (fractions, 10% = 0.10)")
    for dup in _duplicates(p["instrument_id"] for p in portfolio["positions"]):
        errors.append(f"positions: instrument_id {dup!r} appears more than once")
    return errors


def validate_portfolio(portfolio: Any) -> None:
    _raise("portfolio", portfolio_errors(portfolio))


def validate_purchase_request(request: Any) -> None:
    """Shape only, and the target must be a finite number.

    Finite range problems (negative, above 1, below the current weight) are the
    engine's INVALID_REQUEST, not a contract error (D5).
    """
    _raise("purchase_request", schema_errors(request, "purchase_request.schema.json"))


def validate_unresolved_purchase_request(request: Any) -> None:
    _raise("unresolved purchase_request", schema_errors(request, "purchase_request.schema.json#/$defs/unresolved"))


# --------------------------------------------------------------------------- objective / rule / policy

def validate_objective(objective: Any) -> None:
    _raise("objective", schema_errors(objective, "objective.schema.json"))


def rule_errors(rule: Any) -> list[str]:
    """Shape plus the provenance invariants (all expressed in rule.schema.json)."""
    return schema_errors(rule, "rule.schema.json")


def validate_rule(rule: Any) -> None:
    _raise("rule", rule_errors(rule))


def policy_errors(policy: Any, check_hash: bool = True) -> list[str]:
    errors = schema_errors(policy, "policy.schema.json")
    if errors:
        return errors
    version, parent = policy["version"], policy["parent_version"]
    if version == 1 and parent is not None:
        errors.append("parent_version: must be null for version 1")
    if version > 1 and (parent is None or parent >= version):
        errors.append(f"parent_version: must be an earlier version than {version}, got {parent!r}")
    objective_ids = [o["objective_id"] for o in policy["objectives"]]
    for dup in _duplicates(objective_ids):
        errors.append(f"objectives: objective_id {dup!r} appears more than once")
    rules = {r["rule_id"]: r for r in policy["rules"]}
    for dup in _duplicates(r["rule_id"] for r in policy["rules"]):
        errors.append(f"rules: rule_id {dup!r} appears more than once")
    for i, rule in enumerate(policy["rules"]):
        where = f"rules[{i}] ({rule['rule_id']})"
        if rule["objective_id"] is not None and rule["objective_id"] not in objective_ids:
            errors.append(f"{where}: objective_id {rule['objective_id']!r} is not an objective of this version")
        old_id = rule["supersedes_rule_id"]
        if old_id is not None:
            old = rules.get(old_id)
            if old is None or old["status"] != "SUPERSEDED" or old["superseded_by_rule_id"] != rule["rule_id"]:
                errors.append(f"{where}: supersedes_rule_id {old_id!r} must be a SUPERSEDED rule of this version pointing back")
        new_id = rule["superseded_by_rule_id"]
        if new_id is not None:
            new = rules.get(new_id)
            if new is None or new["supersedes_rule_id"] != rule["rule_id"]:
                errors.append(f"{where}: superseded_by_rule_id {new_id!r} must be a rule of this version pointing back")
    if check_hash and policy["content_hash"] != compute_content_hash(policy):
        errors.append(f"content_hash: expected {compute_content_hash(policy)}, got {policy['content_hash']}")
    return errors


def validate_policy(policy: Any, check_hash: bool = True) -> None:
    _raise("policy", policy_errors(policy, check_hash))


# --------------------------------------------------------------------------- data files

def instrument_errors(instrument: Any) -> list[str]:
    errors = schema_errors(instrument, "instrument.schema.json")
    if errors:
        return errors
    is_fund, equity_scope = ASSET_CLASS_FLAGS[instrument["asset_class"]]
    if instrument["is_fund"] != is_fund or instrument["equity_scope"] != equity_scope:
        errors.append(
            f"asset_class {instrument['asset_class']!r} requires is_fund={is_fund} and equity_scope={equity_scope}"
        )
    if (instrument["sector"] is None) != (instrument["sector_source"] is None):
        errors.append("sector and sector_source must both be set or both be null")
    return errors


def validate_instrument(instrument: Any) -> None:
    _raise("instrument", instrument_errors(instrument))


def validate_instrument_registry(registry: Any) -> None:
    errors = schema_errors(registry, "instrument.schema.json#/$defs/registry")
    if not errors:
        for key, entry in registry["instruments"].items():
            if entry["instrument_id"] != key:
                errors.append(f"instruments.{key}: instrument_id {entry['instrument_id']!r} differs from its key")
            errors.extend(f"instruments.{key}: {e}" for e in instrument_errors(entry))
    _raise("instrument registry", errors)


def validate_holdings_snapshot(snapshot: Any) -> None:
    errors = schema_errors(snapshot, "holdings_snapshot.schema.json")
    if not errors:
        for key, fund in snapshot["funds"].items():
            where = f"funds.{key}"
            if fund["fund_id"] != key:
                errors.append(f"{where}: fund_id {fund['fund_id']!r} differs from its key")
            if fund["n_holdings"] != len(fund["holdings"]):
                errors.append(f"{where}: n_holdings {fund['n_holdings']} != {len(fund['holdings'])} rows")
            total = sum(row["weight_fraction"] for row in fund["holdings"])
            if not abs(total - fund["coverage_fraction"]) <= COVERAGE_SUM_TOLERANCE:
                errors.append(f"{where}: coverage_fraction {fund['coverage_fraction']!r} != sum of weights {total!r} (weights are never rescaled)")
            if not fund["coverage_fraction"] <= 1.01:
                errors.append(f"{where}: coverage_fraction {fund['coverage_fraction']!r} > 1.01: weights must be fractions, not percentages")
            for i, row in enumerate(fund["holdings"]):
                if row["fund_id"] != key:
                    errors.append(f"{where}.holdings[{i}]: fund_id {row['fund_id']!r} differs from the fund key")
                if (row["sector"] is None) != (row["sector_source"] is None):
                    errors.append(f"{where}.holdings[{i}]: sector and sector_source must both be set or both be null")
    _raise("holdings snapshot", errors)


def _ascending(series: list, where: str, errors: list[str]) -> None:
    for i in range(1, len(series)):
        if series[i][0] <= series[i - 1][0]:
            errors.append(f"{where}[{i}]: date {series[i][0]} is not after {series[i - 1][0]} (strictly ascending, no duplicates)")
            return


def validate_market_data(market_data: Any) -> None:
    errors = schema_errors(market_data, "market_data.schema.json")
    if not errors:
        for instrument_id, entry in market_data["prices"].items():
            _ascending(entry["series"], f"prices.{instrument_id}.series", errors)
        _ascending(market_data["fx_usdcad"], "fx_usdcad", errors)
    _raise("market data", errors)


def validate_source(source: Any) -> None:
    _raise("source", schema_errors(source, "source.schema.json"))


def validate_source_registry(registry: Any) -> None:
    errors = schema_errors(registry, "source.schema.json#/$defs/registry")
    if not errors:
        for key, entry in registry["sources"].items():
            if entry["source_id"] != key:
                errors.append(f"sources.{key}: source_id {entry['source_id']!r} differs from its key")
    _raise("source registry", errors)


def validate_controversy_record(record: Any) -> None:
    _raise("controversy record", schema_errors(record, "controversy_record.schema.json"))


def validate_controversy_registry(registry: Any, known_source_ids: Optional[Iterable[str]] = None) -> None:
    errors = schema_errors(registry, "controversy_record.schema.json#/$defs/registry")
    if not errors:
        researched = set(registry["registry_scope"]["issuers_researched"])
        known = set(known_source_ids) if known_source_ids is not None else None
        for dup in _duplicates(r["record_id"] for r in registry["records"]):
            errors.append(f"records: record_id {dup!r} appears more than once")
        for i, record in enumerate(registry["records"]):
            if record["issuer_id"] not in researched:
                errors.append(f"records[{i}]: issuer {record['issuer_id']!r} is not listed in registry_scope.issuers_researched")
            if known is not None:
                for source_id in record["source_ids"]:
                    if source_id not in known:
                        errors.append(f"records[{i}]: source_id {source_id!r} is not in the source registry")
    _raise("controversy registry", errors)


def validate_evidence_record(record: Any) -> None:
    _raise("evidence record", schema_errors(record, "evidence_record.schema.json"))
