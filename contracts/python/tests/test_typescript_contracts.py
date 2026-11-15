"""contracts/typescript/contracts.ts mirrors the JSON Schemas (drift test).

The TypeScript file is written by hand, so this test reads it as text and
compares it with the schemas: union members, property names, optional and
nullable members, and the primitive kind of every property. Each interface is
written with one `name: type;` member per line, which is what makes the text
checkable without a TypeScript parser.
"""

from __future__ import annotations

import json
import re

import pytest

import byb_contracts.constants as c
from byb_contracts.schema import load_schema, resolve_ref
from paths import CONTRACTS

TS = (CONTRACTS / "typescript" / "contracts.ts").read_text(encoding="utf-8")

UNIONS = {m.group(1): re.findall(r'"([^"]*)"', m.group(2))
          for m in re.finditer(r"^export type (\w+) =(.*?);", TS, re.S | re.M) if re.fullmatch(r'[\s|]*"[^;]*', m.group(2))}
ALIASES = dict(re.findall(r"^export type (\w+) = (number|string);", TS, re.M))
INTERFACES = {m.group(1): (m.group(2), re.findall(r"^  (\w+)(\??): (.+);$", m.group(3), re.M))
              for m in re.finditer(r"^export interface (\w+)(?: extends (\w+))? \{\n(.*?)^\}", TS, re.S | re.M)}

CR, API, SC, FX = "check_result.schema.json", "api.schema.json", "scenario.schema.json", "fixture.schema.json"
# TypeScript interface -> the schema node it mirrors exactly.
EXACT = {
    "Bounds": "common.schema.json#/$defs/bounds",
    "Position": "portfolio.schema.json#/properties/positions/items",
    "Portfolio": "portfolio.schema.json",
    "Objective": "objective.schema.json",
    "PurchaseRequest": "purchase_request.schema.json",
    "UnresolvedPurchaseRequest": "purchase_request.schema.json#/$defs/unresolved",
    "MaxIssuerExposureParameters": "rule.schema.json#/$defs/max_issuer_exposure_parameters",
    "MinIssuerExposureParameters": "rule.schema.json#/$defs/min_issuer_exposure_parameters",
    "NamedIssuersDefinition": "rule.schema.json#/$defs/exclusion_parameters/properties/definition/oneOf/0",
    "FundReportedSectorDefinition": "rule.schema.json#/$defs/exclusion_parameters/properties/definition/oneOf/1",
    "ExclusionParameters": "rule.schema.json#/$defs/exclusion_parameters",
    "ControversyCriteria": "rule.schema.json#/$defs/controversy_exclusion_parameters/properties/criteria",
    "ControversyExclusionParameters": "rule.schema.json#/$defs/controversy_exclusion_parameters",
    "ScenarioLossBudgetParameters": "rule.schema.json#/$defs/scenario_loss_budget_parameters",
    "Policy": "policy.schema.json",
    "Instrument": "instrument.schema.json",
    "InstrumentRegistry": "instrument.schema.json#/$defs/registry",
    "Holding": "holdings_snapshot.schema.json#/$defs/holding",
    "FundHoldings": "holdings_snapshot.schema.json#/$defs/fund",
    "HoldingsSnapshot": "holdings_snapshot.schema.json",
    "PriceSeries": "market_data.schema.json#/properties/prices/additionalProperties",
    "MarketData": "market_data.schema.json",
    "ControversyRecord": "controversy_record.schema.json",
    "ControversyRegistryScope": "controversy_record.schema.json#/$defs/registry/properties/registry_scope",
    "ControversyRegistry": "controversy_record.schema.json#/$defs/registry",
    "Source": "source.schema.json",
    "SourceRegistry": "source.schema.json#/$defs/registry",
    "EvidenceSubject": "evidence_record.schema.json#/properties/subject",
    "AsOfPeriod": "evidence_record.schema.json#/properties/period/oneOf/0",
    "RangePeriod": "evidence_record.schema.json#/properties/period/oneOf/1",
    "EvidenceRecord": "evidence_record.schema.json",
    "Execution": f"{CR}#/properties/execution",
    "Feasibility": f"{CR}#/properties/feasibility/anyOf/1",
    "PolicyConflict": f"{CR}#/$defs/conflict",
    "PolicyConsistency": f"{CR}#/properties/policy_consistency",
    "BreachingSubject": f"{CR}#/$defs/breaching_subject",
    "RuleEvaluationSnapshot": f"{CR}#/$defs/rule_evaluation_snapshot",
    "OutOfScopePosition": f"{CR}#/$defs/rule_result/properties/out_of_scope/items",
    "RuleResult": f"{CR}#/$defs/rule_result",
    "RuleNotEvaluated": f"{CR}#/properties/rules_not_evaluated/items",
    "PurchaseEffect": f"{CR}#/$defs/starting_finding/properties/purchase_effect",
    "StartingFinding": f"{CR}#/$defs/starting_finding",
    "FundCoverage": f"{CR}#/$defs/fund_coverage",
    "ScenarioMeasures": f"{CR}#/$defs/scenario_measures",
    "InstrumentReturn": f"{CR}#/$defs/scenario/properties/instrument_returns/items",
    "ScenarioResult": f"{CR}#/$defs/scenario",
    "GoalContext": f"{CR}#/$defs/goal_context",
    "BindingConstraint": f"{CR}#/$defs/max_compliant/properties/binding_constraint/anyOf/1",
    "IndirectExposure": f"{CR}#/$defs/exposure_breakdown/properties/indirect_by_fund/items",
    "ExposureBreakdown": f"{CR}#/$defs/exposure_breakdown",
    "PossibleExtra": f"{CR}#/$defs/exposure/properties/possible_extra",
    "IssuerExposure": f"{CR}#/$defs/exposure/properties/issuers/items",
    "Exposure": f"{CR}#/$defs/exposure",
    "SummaryCounts": f"{CR}#/$defs/summary/properties/counts",
    "Summary": f"{CR}#/$defs/summary",
    "CheckResult": CR,
    "UnsupportedRequest": "interpretation.schema.json#/properties/unsupported/items",
    "ClarificationOption": "interpretation.schema.json#/$defs/clarification_option",
    "Clarification": "interpretation.schema.json#/$defs/clarification",
    "Interpretation": "interpretation.schema.json",
    "CorrectFactPayload": "challenge.schema.json#/$defs/correct_fact_payload",
    "ClarifyPreferencePayload": "challenge.schema.json#/$defs/clarify_preference_payload",
    "ChangeRulePayload": "challenge.schema.json#/$defs/change_rule_payload",
    "CorrectionProvenance": "challenge.schema.json#/$defs/proposed_correction/properties/provenance",
    "ProposedCorrection": "challenge.schema.json#/$defs/proposed_correction",
    "InvestigationAgent": "investigation_job.schema.json#/properties/agent",
    "InvestigationStep": "investigation_job.schema.json#/$defs/step",
    "ExplanationStatement": "investigation_job.schema.json#/$defs/statement",
    "InvestigationFailure": "investigation_job.schema.json#/properties/failure/anyOf/1",
    "InvestigationJob": "investigation_job.schema.json",
    "PersonaFact": f"{SC}#/properties/persona/properties/facts/items",
    "PersonaTests": f"{SC}#/properties/persona/properties/what_this_persona_tests",
    "Persona": f"{SC}#/properties/persona",
    "AlternativeRuleSet": f"{SC}#/properties/alternative_rule_sets/items",
    "DemoPhrase": f"{SC}#/properties/demo_phrases/items",
    "DemoRequest": f"{SC}#/properties/demo_requests/items",
    "DemoChallenge": f"{SC}#/properties/demo_challenge/anyOf/1",
    "DemoStep": f"{SC}#/properties/demo_steps/items",
    "Scenario": SC,
    "ErrorDetail": f"{API}#/$defs/error_response/properties/error/properties/details/items",
    "ErrorBody": f"{API}#/$defs/error_response/properties/error",
    "ErrorResponse": f"{API}#/$defs/error_response",
    "PortfolioResponse": f"{API}#/$defs/portfolio_response",
    "InterpretRequest": f"{API}#/$defs/interpret_request",
    "RuleConfirmation": f"{API}#/$defs/confirm_request/properties/confirmations/items",
    "ConfirmRequest": f"{API}#/$defs/confirm_request",
    "ConfirmResponse": f"{API}#/$defs/confirm_response",
    "CheckRequest": f"{API}#/$defs/check_request",
    "InvestigationCreateRequest": f"{API}#/$defs/investigation_create_request",
    "PollInstruction": f"{API}#/$defs/investigation_accepted/properties/poll",
    "InvestigationAccepted": f"{API}#/$defs/investigation_accepted",
    "ChallengeResponse": f"{API}#/$defs/challenge_response",
    "ApiFixture": f"{FX}#/$defs/api_fixture",
    "EngineUniverse": f"{FX}#/$defs/engine_universe",
    "EngineFixtureInputs": f"{FX}#/$defs/engine_fixture/properties/inputs",
    "EngineFixture": f"{FX}#/$defs/engine_fixture",
}
# Variants of a discriminated union: own members plus those of the base interface mirror one schema node.
VARIANTS = {
    **{name: "rule.schema.json" for name in ("MaxIssuerExposureRule", "MinIssuerExposureRule", "ExclusionRule", "ControversyExclusionRule", "ScenarioLossBudgetRule")},
    **{name: f"{CR}#/$defs/max_compliant" for name in ("MaxCompliantSupported", "MaxCompliantWithheld", "MaxCompliantNoFeasiblePurchase")},
    **{name: "challenge.schema.json" for name in ("CorrectFactChallenge", "ClarifyPreferenceChallenge", "ChangeRuleChallenge")},
    **{name: f"{API}#/$defs/challenge_request" for name in ("CorrectFactChallengeRequest", "ClarifyPreferenceChallengeRequest", "ChangeRuleChallengeRequest")},
}
BASES = {"RuleBase", "ChallengeBase"}


def node(ref):
    return resolve_ref(ref, ref.partition("#")[0])


def follow(schema, file_name):
    while "$ref" in schema:
        schema, file_name = resolve_ref(schema["$ref"], file_name)
    return schema, file_name


def allows_null(schema, file_name):
    schema, file_name = follow(schema, file_name)
    kinds = schema.get("type")
    if kinds == "null" or (isinstance(kinds, list) and "null" in kinds):
        return True
    return any(allows_null(branch, file_name) for word in ("anyOf", "oneOf") for branch in schema.get(word, []))


def schema_kind(schema, file_name):
    """number, string, boolean, array, object, mixed or null: the primitive kind of a schema, ignoring null."""
    schema, file_name = follow(schema, file_name)
    if "const" in schema:
        return {bool: "boolean", str: "string"}.get(type(schema["const"]), "number")
    if "enum" in schema:
        return "string"
    for word in ("anyOf", "oneOf"):
        if word in schema:
            kinds = {schema_kind(branch, file_name) for branch in schema[word]} - {"null"}
            return kinds.pop() if len(kinds) == 1 else "mixed"
    kinds = schema.get("type", "object")
    kinds = {"number" if k == "integer" else k for k in ([kinds] if isinstance(kinds, str) else kinds)} - {"null"}
    if not kinds:
        return "null"
    return kinds.pop() if len(kinds) == 1 else "mixed"


def ts_kind(text):
    kinds = set()
    for part in (p.strip() for p in text.split("|")):
        if part == "null":
            continue
        if part.endswith("[]"):
            kinds.add("array")
        elif part == "number" or ALIASES.get(part) == "number":
            kinds.add("number")
        elif part == "string" or part.startswith('"') or ALIASES.get(part) == "string" or part in UNIONS:
            kinds.add("string")
        elif part in ("boolean", "true", "false"):
            kinds.add("boolean")
        else:
            kinds.add("object")
    if not kinds:
        return "null"
    return kinds.pop() if len(kinds) == 1 else "mixed"


def ts_nullable(text):
    return "null" in [p.strip() for p in text.split("|")]


def members(name):
    parent, own = INTERFACES[name]
    return (INTERFACES[parent][1] if parent else []) + own


def pascal(snake):
    return "".join(word.capitalize() for word in snake.split("_"))


def test_the_file_was_parsed():
    """Guards against a regular expression that silently matches nothing."""
    assert len(INTERFACES) >= 110 and len(UNIONS) >= 45
    assert sum(len(m) for _, m in INTERFACES.values()) >= 450
    assert len(re.findall(r"^export interface ", TS, re.M)) == len(INTERFACES), "an interface is not written in the checkable form"
    assert ALIASES["Fraction"] == "number" and ALIASES["IsoDate"] == "string"


def test_every_interface_is_checked_against_a_schema():
    assert set(INTERFACES) == set(EXACT) | set(VARIANTS) | BASES
    assert not set(EXACT) & set(VARIANTS)


def test_every_schema_enum_is_a_union_with_the_same_members():
    common = load_schema("common.schema.json")["$defs"]
    enums = {name: definition["enum"] for name, definition in common.items() if "enum" in definition}
    assert len(enums) == len(c.SCHEMA_ENUMS) == 42  # counted in common.schema.json: 42 definitions carry an enum
    for name, values in enums.items():
        assert UNIONS.get(pascal(name)) == values, f"{pascal(name)} differs from common.schema.json#/$defs/{name}"
    assert UNIONS["Funding"] == [common["funding"]["const"]]
    assert UNIONS["SchemaVersion"] == [common["schema_version"]["const"]]
    assert UNIONS["DemoPhraseOutcome"] == node(f"{SC}#/properties/demo_phrases/items/properties/expected_outcome")[0]["enum"]
    known = {pascal(name) for name in enums} | {"Funding", "SchemaVersion", "DemoPhraseOutcome"}
    assert set(UNIONS) == known, "a string union in contracts.ts has no schema enum behind it"


@pytest.mark.parametrize("name", sorted(EXACT))
def test_interface_mirrors_its_schema(name):
    schema, file_name = follow(*node(EXACT[name]))
    properties, required = schema["properties"], set(schema.get("required", []))
    found = members(name)
    assert [n for n, _, _ in found] == list(dict.fromkeys(n for n, _, _ in found)), "duplicate member"
    assert {n for n, _, _ in found} == set(properties), f"{name}: members differ from {EXACT[name]}"
    for member, optional, text in found:
        where = f"{name}.{member}"
        assert (optional == "?") == (member not in required), f"{where}: optional marker does not match `required`"
        assert ts_nullable(text) == allows_null(properties[member], file_name), f"{where}: nullability differs"
        assert ts_kind(text) == schema_kind(properties[member], file_name), f"{where}: `{text}` is not what the schema says"
        constant = follow(properties[member], file_name)[0].get("const", ...)
        if constant is not ...:
            assert text == json.dumps(constant) or UNIONS.get(text) == [constant], f"{where}: the schema fixes the value {constant!r}"


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_variant_mirrors_its_schema(name):
    schema, file_name = follow(*node(VARIANTS[name]))
    properties = schema["properties"]
    found = members(name)
    assert {n for n, _, _ in found} == set(properties) == set(schema["required"]), f"{name}: members differ from {VARIANTS[name]}"
    for member, optional, text in found:
        where = f"{name}.{member}"
        assert optional == "", where
        if ts_nullable(text):
            assert allows_null(properties[member], file_name), f"{where}: the schema never allows null here"
        if ts_kind(text) != "null":
            assert ts_kind(text) == schema_kind(properties[member], file_name), f"{where}: `{text}` is not what the schema says"


def test_rule_variants_follow_the_rule_schema_conditions():
    conditions = [entry for entry in load_schema("rule.schema.json")["allOf"] if "rule_type" in entry["if"]["properties"]]
    assert len(conditions) == len(c.RULE_TYPES) == 5
    for entry in conditions:
        rule_type = entry["if"]["properties"]["rule_type"]["const"]
        variant = {n: text for n, _, text in members(pascal(rule_type) + "Rule")}
        assert variant["rule_type"] == json.dumps(rule_type)
        assert variant["threshold_kind"] == json.dumps(entry["then"]["properties"]["threshold_kind"]["const"]) == json.dumps(c.THRESHOLD_KIND_BY_RULE_TYPE[rule_type])
        assert entry["then"]["properties"]["parameters"]["$ref"] == f"#/$defs/{rule_type}_parameters"
        assert variant["parameters"] == pascal(rule_type) + "Parameters"
    union = re.search(r"^export type Rule =(.*?);", TS, re.S | re.M).group(1)
    assert re.findall(r"\w+", union) == [pascal(rule_type) + "Rule" for rule_type in c.RULE_TYPES]


def test_max_compliant_variants_follow_the_schema_conditions():
    by_status = {dict((n, t) for n, _, t in members(name))["status"]: dict((n, t) for n, _, t in members(name))
                 for name in ("MaxCompliantSupported", "MaxCompliantWithheld", "MaxCompliantNoFeasiblePurchase")}
    assert set(by_status) == {json.dumps(status) for status in c.MAX_COMPLIANT_STATUSES}
    supported, withheld, none = by_status['"SUPPORTED"'], by_status['"WITHHELD"'], by_status['"NO_FEASIBLE_PURCHASE"']
    assert (supported["final_direct_weight"], supported["additional_purchase"], supported["verified_by_rerun"]) == ("Fraction", "Fraction", "true")
    assert supported["binding_constraint"] == none["binding_constraint"] == "BindingConstraint" and withheld["binding_constraint"] == "null"
    for variant in (withheld, none):
        assert (variant["final_direct_weight"], variant["additional_purchase"], variant["verified_by_rerun"]) == ("null", "null", "false")


def test_challenge_variants_pair_each_type_with_its_payload():
    for prefix, challenge_type in (("CorrectFact", "CORRECT_FACT"), ("ClarifyPreference", "CLARIFY_PREFERENCE"), ("ChangeRule", "CHANGE_RULE")):
        for suffix in ("Challenge", "ChallengeRequest"):
            variant = {n: text for n, _, text in members(prefix + suffix)}
            assert variant["type"] == json.dumps(challenge_type) and variant["payload"] == prefix + "Payload"
    assert [pascal(t.lower()) for t in c.CHALLENGE_TYPES] == ["CorrectFact", "ClarifyPreference", "ChangeRule"]


def test_constants_equal_the_python_constants():
    def constant(name):
        return re.search(rf"^export const {name} = (.+);$", TS, re.M).group(1)

    assert constant("SCHEMA_VERSION") == json.dumps(c.SCHEMA_VERSION)
    assert float(constant("EPS")) == c.EPS
    assert constant("ISSUER_SCOPE_ANY") == json.dumps(c.ISSUER_SCOPE_ANY)
    assert int(constant("POLL_INTERVAL_MS")) == c.POLL_INTERVAL_MS
    assert int(constant("POLL_DEADLINE_MS")) == c.POLL_DEADLINE_SECONDS * 1000
    assert c.POLL_DEADLINE_SECONDS > c.INVESTIGATION_DEADLINE_SECONDS, "the client must outlast the job deadline"
    pattern = load_schema("investigation_job.schema.json")["properties"]["idempotency_key"]["pattern"]
    assert constant("IDEMPOTENCY_KEY_PATTERN") == f"/{pattern}/"
    assert re.search(r'^export const TERMINAL_JOB_STATUSES: readonly JobStatus\[\] = \["SUCCEEDED", "FAILED"\];$', TS, re.M)
    assert list(c.TERMINAL_JOB_STATUSES) == ["SUCCEEDED", "FAILED"]
