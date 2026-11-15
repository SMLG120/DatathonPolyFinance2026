"""The same documents validated with the reference `jsonschema` implementation (draft 2020-12).

Skipped as a whole when the `jsonschema` package is not importable; the
standard-library validation in test_fixtures_validate.py always runs.
"""

from __future__ import annotations

import copy

import pytest

jsonschema = pytest.importorskip("jsonschema")
referencing = pytest.importorskip("referencing")

import byb_contracts as byb  # noqa: E402
from negative_examples import SCHEMA_NEGATIVES, valid_documents  # noqa: E402
from paths import API_FIXTURES, CASES, REQUEST_SCHEMAS, SCENARIOS, SCHEMAS, UNIVERSES, load  # noqa: E402

BASE = "https://before-you-buy.invalid/contracts/schemas/"
SCHEMA_DOCS = {path.name: load(path) for path in sorted(SCHEMAS.glob("*.schema.json"))}
REGISTRY = referencing.Registry().with_resources(
    (document["$id"], referencing.Resource.from_contents(document)) for document in SCHEMA_DOCS.values()
)


def reference_errors(value, ref):
    validator = jsonschema.Draft202012Validator({"$ref": BASE + ref}, registry=REGISTRY)
    return [f"{'/'.join(map(str, error.absolute_path)) or '$'}: {error.message}" for error in validator.iter_errors(value)]


def refs_in(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from refs_in(value)
    elif isinstance(node, list):
        for item in node:
            yield from refs_in(item)


def test_there_are_schema_files():
    names = ["api", "challenge", "check_result", "common", "controversy_record", "evidence_record", "fixture", "holdings_snapshot",
             "instrument", "interpretation", "investigation_job", "market_data", "objective", "policy", "portfolio", "purchase_request",
             "rule", "scenario", "source"]
    assert sorted(SCHEMA_DOCS) == [f"{name}.schema.json" for name in names]
    assert sorted(SCHEMA_DOCS) == byb.schema_files()


@pytest.mark.parametrize("name", sorted(SCHEMA_DOCS))
def test_schema_file_is_valid_draft_2020_12(name):
    document = SCHEMA_DOCS[name]
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert document["$id"] == BASE + name
    jsonschema.Draft202012Validator.check_schema(document)
    resolver = REGISTRY.resolver(document["$id"])
    for ref in refs_in(document):
        resolver.lookup(ref)  # raises if a $ref points nowhere


@pytest.mark.parametrize("path", UNIVERSES, ids=[p.stem for p in UNIVERSES])
def test_engine_universe(path):
    assert reference_errors(load(path), "fixture.schema.json#/$defs/engine_universe") == []


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_engine_case(path):
    assert reference_errors(load(path), "fixture.schema.json#/$defs/engine_fixture") == []


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario(path):
    assert reference_errors(load(path), "scenario.schema.json") == []


@pytest.mark.parametrize("path", API_FIXTURES, ids=[p.stem for p in API_FIXTURES])
def test_api_fixture(path):
    fixture = load(path)
    assert reference_errors(fixture, "fixture.schema.json#/$defs/api_fixture") == []
    assert reference_errors(fixture["response_body"], fixture["response_schema"]) == []
    request_schema = REQUEST_SCHEMAS.get(fixture["route"])
    if request_schema and fixture["http_status"] != 400:
        assert reference_errors(fixture["request_body"], request_schema) == []
    if request_schema and fixture["http_status"] == 400:
        assert reference_errors(fixture["request_body"], request_schema) != []


VALID = valid_documents()


@pytest.mark.parametrize("label", sorted(VALID))
def test_both_validators_accept_the_valid_documents(label):
    ref, document = VALID[label]
    assert byb.schema_errors(document, ref) == []
    assert reference_errors(document, ref) == []


@pytest.mark.parametrize("label,base,mutate", SCHEMA_NEGATIVES, ids=[n[0] for n in SCHEMA_NEGATIVES])
def test_both_validators_reject_the_same_broken_documents(label, base, mutate):
    ref, document = VALID[base]
    broken = copy.deepcopy(document)
    mutate(broken)
    ours = byb.schema_errors(broken, ref)
    theirs = reference_errors(broken, ref)
    assert ours, f"{label}: the standard-library validator accepted a broken document"
    assert theirs, f"{label}: jsonschema accepted a broken document"
