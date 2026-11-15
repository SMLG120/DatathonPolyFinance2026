"""The Python constants equal the enumerations of contracts/schemas/common.schema.json (drift test)."""

from __future__ import annotations

import byb_contracts.constants as c
from byb_contracts.schema import load_schema

COMMON = load_schema("common.schema.json")["$defs"]


def test_every_schema_enum_has_a_constant_with_the_same_members_in_the_same_order():
    enums = {name: definition["enum"] for name, definition in COMMON.items() if "enum" in definition}
    assert set(enums) == set(c.SCHEMA_ENUMS), "an enum exists on one side only"
    for name, values in c.SCHEMA_ENUMS.items():
        assert list(values) == enums[name], f"constants differ from common.schema.json#/$defs/{name}"


def test_single_value_constants_equal_the_schema():
    assert c.SCHEMA_VERSION == COMMON["schema_version"]["const"]
    assert c.FUNDING == COMMON["funding"]["const"]
    assert c.UNIT_FRACTION == load_schema("rule.schema.json")["properties"]["unit"]["const"]
    assert c.BASE_CURRENCY == load_schema("portfolio.schema.json")["properties"]["base_currency"]["const"]
    assert set(c.THRESHOLD_KIND_BY_RULE_TYPE) == set(c.RULE_TYPES) == set(c.MAX_TYPE_RULES) | set(c.MIN_TYPE_RULES)
    assert set(c.TERMINAL_JOB_STATUSES) < set(c.JOB_STATUSES)
    assert c.POLL_INTERVAL_MS >= load_schema("api.schema.json")["$defs"]["investigation_accepted"]["properties"]["poll"]["properties"]["interval_ms"]["minimum"]
    assert c.INTERPRET_TIMEOUT_SECONDS < 30, "API Gateway HTTP APIs cut an integration at 30 s"
