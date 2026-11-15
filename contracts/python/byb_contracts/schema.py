"""Minimal JSON Schema (draft 2020-12 subset) validator. Standard library only.

The JSON files in ``contracts/schemas`` are the single source of truth for
shapes. This module interprets exactly the keywords those files use, so the
Python validators can never drift from the schemas. An unsupported keyword
raises ``SchemaUsageError`` instead of being silently ignored.

Schema directory resolution, first match wins:
1. the ``BYB_SCHEMA_DIR`` environment variable,
2. a ``schemas`` folder next to this file (a bundled copy, e.g. in a Lambda zip),
3. ``contracts/schemas`` in the repository layout.

Numbers: every number in every document is a finite IEEE-754 double
(contracts/SEMANTICS.md section 2). Python's ``float`` also holds NaN and
+/-Infinity, which JSON cannot represent and for which every comparison is
False (so ``minimum`` / ``maximum`` would let NaN through). ``schema_errors``
therefore rejects any non-finite float anywhere in the document before it looks
at the schema, and ``type: number`` never matches one.
"""

from __future__ import annotations

import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_ANNOTATIONS = {"$schema", "$id", "$defs", "title", "description", "$comment", "examples", "default"}
_SUPPORTED = {
    "$ref", "type", "enum", "const", "required", "properties", "additionalProperties", "propertyNames",
    "items", "prefixItems", "minItems", "maxItems", "uniqueItems", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "minLength", "maxLength", "pattern", "allOf", "anyOf", "oneOf", "if", "then", "else",
}


class SchemaUsageError(Exception):
    """The schema itself uses something this validator does not implement."""


def schema_dir() -> Path:
    env = os.environ.get("BYB_SCHEMA_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    bundled = here / "schemas"
    if bundled.is_dir():
        return bundled
    return here.parent.parent / "schemas"


def _reject_constant(token: str) -> Any:
    raise ValueError(f"{token} is not valid JSON: every number must be finite")


@lru_cache(maxsize=None)
def load_schema(file_name: str) -> dict:
    path = schema_dir() / file_name
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, parse_constant=_reject_constant)


def schema_files() -> list[str]:
    return sorted(p.name for p in schema_dir().glob("*.schema.json"))


def _pointer(document: Any, pointer: str) -> Any:
    node = document
    if pointer in ("", "/"):
        return node
    for raw in pointer.lstrip("/").split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(key)] if isinstance(node, list) else node[key]
    return node


def resolve_ref(ref: str, current_file: str) -> tuple[dict, str]:
    """Return (schema node, file it lives in) for a ``$ref`` used in these contracts."""
    file_part, _, fragment = ref.partition("#")
    target_file = file_part or current_file
    if "/" in target_file:
        target_file = target_file.rsplit("/", 1)[1]
    return _pointer(load_schema(target_file), fragment), target_file


def _type_ok(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (isinstance(value, float) and value.is_integer())
    if name == "number":
        return _is_number(value)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    raise SchemaUsageError(f"unknown type name {name!r}")


def _is_number(value: Any) -> bool:
    """A JSON number: an int or a finite float. Never a bool, never NaN or +/-Infinity."""
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, float) and math.isfinite(value))


def non_finite_errors(value: Any, path: str = "") -> list[str]:
    """One error per NaN, +Infinity or -Infinity found anywhere in ``value``, each naming its path.

    Non-finite numbers are invalid input. They are never missing data (that is
    an explicit ``null``) and are never coerced to zero.
    """
    if isinstance(value, float):
        if math.isfinite(value):
            return []
        shown = "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
        return [f"{path or '$'}: {shown} is not a finite number (NaN and +/-Infinity are invalid input, not missing data)"]
    errors: list[str] = []
    if isinstance(value, dict):
        for name, item in value.items():
            errors.extend(non_finite_errors(item, f"{path}.{name}" if path else str(name)))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            errors.extend(non_finite_errors(item, f"{path}[{i}]"))
    return errors


def _json_equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_number(a) and _is_number(b):
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    return a == b


def _check(value: Any, schema: Any, file_name: str, path: str, errors: list[str]) -> None:
    if schema is True:
        return
    if schema is False:
        errors.append(f"{path or '$'}: no value is allowed here")
        return
    unknown = set(schema) - _SUPPORTED - _ANNOTATIONS
    if unknown:
        raise SchemaUsageError(f"{file_name}: unsupported keyword(s) {sorted(unknown)} at {path or '$'}")
    where = path or "$"

    if "$ref" in schema:
        target, target_file = resolve_ref(schema["$ref"], file_name)
        _check(value, target, target_file, path, errors)

    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, n) for n in names):
            errors.append(f"{where}: expected {' or '.join(names)}, got {type(value).__name__} ({_short(value)})")
            return
    if "enum" in schema and not any(_json_equal(value, option) for option in schema["enum"]):
        errors.append(f"{where}: {_short(value)} is not one of {schema['enum']}")
    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append(f"{where}: must be {schema['const']!r}, got {_short(value)}")

    if _is_number(value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{where}: {value} is below the minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{where}: {value} is above the maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{where}: {value} must be greater than {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            errors.append(f"{where}: {value} must be less than {schema['exclusiveMaximum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{where}: string shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{where}: string longer than {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{where}: {_short(value)} does not match pattern {schema['pattern']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{where}: needs at least {schema['minItems']} item(s), has {len(value)}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{where}: allows at most {schema['maxItems']} item(s), has {len(value)}")
        if schema.get("uniqueItems"):
            for i, item in enumerate(value):
                if any(_json_equal(item, other) for other in value[:i]):
                    errors.append(f"{where}: duplicate item {_short(item)}")
                    break
        prefix = schema.get("prefixItems", [])
        for i, sub in enumerate(prefix[: len(value)]):
            _check(value[i], sub, file_name, f"{path}[{i}]", errors)
        if "items" in schema:
            for i in range(len(prefix), len(value)):
                _check(value[i], schema["items"], file_name, f"{path}[{i}]", errors)

    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{where}: missing required property '{name}'")
        props = schema.get("properties", {})
        for name, sub in props.items():
            if name in value:
                _check(value[name], sub, file_name, f"{path}.{name}" if path else name, errors)
        if "propertyNames" in schema:
            for name in value:
                _check(name, schema["propertyNames"], file_name, f"{path}.<key {name}>" if path else f"<key {name}>", errors)
        if "additionalProperties" in schema:
            extra = schema["additionalProperties"]
            for name in value:
                if name in props:
                    continue
                if extra is False:
                    errors.append(f"{where}: unexpected property '{name}'")
                else:
                    _check(value[name], extra, file_name, f"{path}.{name}" if path else name, errors)

    for sub in schema.get("allOf", []):
        _check(value, sub, file_name, path, errors)
    if "anyOf" in schema:
        attempts = [_errors_for(value, sub, file_name, path) for sub in schema["anyOf"]]
        if all(attempts):
            errors.append(f"{where}: matches none of the allowed alternatives ({'; '.join(min(attempts, key=len)[:3])})")
    if "oneOf" in schema:
        attempts = [_errors_for(value, sub, file_name, path) for sub in schema["oneOf"]]
        matches = sum(1 for a in attempts if not a)
        if matches == 0:
            errors.append(f"{where}: matches none of the allowed alternatives ({'; '.join(min(attempts, key=len)[:3])})")
        elif matches > 1:
            errors.append(f"{where}: matches {matches} alternatives, exactly one is allowed")
    if "if" in schema:
        if not _errors_for(value, schema["if"], file_name, path):
            if "then" in schema:
                _check(value, schema["then"], file_name, path, errors)
        elif "else" in schema:
            _check(value, schema["else"], file_name, path, errors)


def _errors_for(value: Any, schema: Any, file_name: str, path: str) -> list[str]:
    found: list[str] = []
    _check(value, schema, file_name, path, found)
    return found


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= 60 else text[:57] + "..."


def schema_errors(value: Any, schema_ref: str) -> list[str]:
    """Validate ``value`` against e.g. ``'rule.schema.json'`` or ``'api.schema.json#/$defs/error_response'``.

    A non-finite float anywhere in ``value`` is reported first and on its own:
    no schema keyword can be evaluated meaningfully against NaN.
    """
    errors = non_finite_errors(value)
    if errors:
        return errors
    node, file_name = resolve_ref(schema_ref, schema_ref.partition("#")[0])
    return _errors_for(value, node, file_name, "")
