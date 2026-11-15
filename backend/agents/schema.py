"""A small JSON Schema subset validator (standard library only).

Tool arguments come from a model and are untrusted. They are validated against
the tool's input schema before any tool code runs. Only the keywords listed in
``SUPPORTED_KEYWORDS`` are implemented; :func:`assert_supported` rejects a
schema that uses anything else, so a keyword can never be silently ignored.
"""

from __future__ import annotations

import math
import re
from typing import Any

SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "enum",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "pattern",
        "items",
        "minItems",
        "maxItems",
        "description",
        "title",
    }
)
_TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})
MAX_ERRORS = 8


def assert_supported(schema: Any, path: str = "$") -> None:
    """Raise ``ValueError`` if ``schema`` uses a keyword this validator ignores."""
    if not isinstance(schema, dict):
        raise ValueError(f"{path}: a schema must be an object")
    unknown = sorted(set(schema) - SUPPORTED_KEYWORDS)
    if unknown:
        raise ValueError(f"{path}: unsupported schema keyword(s): {', '.join(unknown)}")
    declared = schema.get("type")
    for name in [declared] if isinstance(declared, str) else list(declared or []):
        if name not in _TYPES:
            raise ValueError(f"{path}: unknown type {name!r}")
    if "pattern" in schema:
        re.compile(_python_pattern(schema["pattern"]))
    extra = schema.get("additionalProperties")
    if extra is not None and not isinstance(extra, bool):
        raise ValueError(f"{path}: additionalProperties must be true or false")
    for name, child in (schema.get("properties") or {}).items():
        assert_supported(child, f"{path}.{name}")
    if "items" in schema:
        assert_supported(schema["items"], f"{path}[]")


def _python_pattern(pattern: str) -> str:
    # JSON Schema uses ECMA-262 semantics, where "$" matches only at the very
    # end. In Python "$" also matches before a trailing newline, so "NVDA\n"
    # would pass "^[A-Z]+$". Translate a trailing "$" to "\Z" to close that gap.
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        return pattern[:-1] + r"\Z"
    return pattern


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _matches_type(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "number":
        return _is_number(value) and math.isfinite(value)
    if name == "integer":
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and math.isfinite(value) and value.is_integer())
    return False


def validate(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Return a list of human-readable problems; empty means valid.

    Messages name the location and the rule, never the offending value, so a
    hostile argument is not echoed into logs or back to the model.
    """
    errors: list[str] = []
    _validate(instance, schema, path, errors)
    return errors[:MAX_ERRORS]


def _validate(instance: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    if len(errors) >= MAX_ERRORS:
        return
    declared = schema.get("type")
    if declared is not None:
        names = [declared] if isinstance(declared, str) else list(declared)
        if not any(_matches_type(instance, name) for name in names):
            errors.append(f"{path}: expected {' or '.join(names)}")
            return
    if "enum" in schema and not any(_same(instance, option) for option in schema["enum"]):
        errors.append(f"{path}: not one of the allowed values")
        return
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and re.search(_python_pattern(schema["pattern"]), instance) is None:
            errors.append(f"{path}: does not match the required pattern")
    elif _is_number(instance):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below the minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above the maximum {schema['maximum']}")
    elif isinstance(instance, dict):
        properties = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in instance:
                errors.append(f"{path}.{name}: required property is missing")
        if schema.get("additionalProperties") is False:
            for name in sorted(set(instance) - set(properties)):
                errors.append(f"{path}: unexpected property {_printable(name)}")
        for name, child in properties.items():
            if name in instance:
                _validate(instance[name], child, f"{path}.{name}", errors)
    elif isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for index, item in enumerate(instance):
                _validate(item, schema["items"], f"{path}[{index}]", errors)


def _same(left: Any, right: Any) -> bool:
    # True == 1 in Python; JSON Schema treats them as different values.
    return type(left) is type(right) and left == right


def _printable(name: Any) -> str:
    text = str(name)[:40]
    return "".join(ch if ch.isalnum() or ch in "_-." else "?" for ch in text)
