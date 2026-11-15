"""Structured logging: one JSON object per line on stdout.

Lambda (Text log format) stores each line as one CloudWatch event, so the
lines can be searched with a JSON filter pattern such as
``{ $.event = "tool_event" }``.

Rules enforced here rather than left to callers:

* values under a sensitive key (authorization, token, access code, ...) are
  replaced, never written;
* long strings are truncated, so a full prompt or model answer cannot end up
  in the log by accident;
* a value that cannot be serialized is replaced by its type name.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

# Exact (case-insensitive) key names. Exact match on purpose: "input_tokens"
# and "max_tokens" are usage counters and must stay readable.
SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "token",
        "bearer",
        "secret",
        "password",
        "access_code",
        "accesscode",
        "api_key",
        "x-api-key",
        "identitysource",
        "identity_source",
    }
)
REDACTED = "[REDACTED]"
MAX_STRING = 400
MAX_ITEMS = 40
MAX_DEPTH = 6

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}

_context: dict[str, Any] = {}
_threshold = _LEVELS["INFO"]
_stream = None  # None means "whatever sys.stdout is at call time"


def configure(level: str = "INFO", stream=None) -> None:
    global _threshold, _stream
    _threshold = _LEVELS.get(str(level).upper(), _LEVELS["INFO"])
    _stream = stream


def bind(**fields: Any) -> None:
    """Replace the per-invocation context added to every line."""
    _context.clear()
    _context.update({k: v for k, v in fields.items() if v is not None})


def add_context(**fields: Any) -> None:
    _context.update({k: v for k, v in fields.items() if v is not None})


def _clean(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else str(value)
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            return value[:MAX_STRING] + f"...[{len(value) - MAX_STRING} more chars]"
        return value
    if depth >= MAX_DEPTH:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_ITEMS:
                cleaned["..."] = f"{len(value) - MAX_ITEMS} more keys"
                break
            name = str(key)
            cleaned[name] = REDACTED if name.lower() in SENSITIVE_KEYS else _clean(item, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        cleaned_items = [_clean(item, depth + 1) for item in items[:MAX_ITEMS]]
        if len(items) > MAX_ITEMS:
            cleaned_items.append(f"...{len(items) - MAX_ITEMS} more items")
        return cleaned_items
    return f"<{type(value).__name__}>"


def emit(level: str, event: str, **fields: Any) -> None:
    if _LEVELS.get(level, 20) < _threshold:
        return
    record: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
        "level": level,
        "event": event,
    }
    record.update(_clean(dict(_context)))
    record.update(_clean(fields))
    stream = _stream if _stream is not None else sys.stdout
    stream.write(json.dumps(record, separators=(",", ":"), ensure_ascii=True) + "\n")
    stream.flush()


def info(event: str, **fields: Any) -> None:
    emit("INFO", event, **fields)


def warning(event: str, **fields: Any) -> None:
    emit("WARNING", event, **fields)


def error(event: str, **fields: Any) -> None:
    emit("ERROR", event, **fields)


def debug(event: str, **fields: Any) -> None:
    emit("DEBUG", event, **fields)
