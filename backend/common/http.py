"""HTTP response helpers for API Gateway HTTP API (payload format 2.0)."""

from __future__ import annotations

import json
from typing import Any

_BASE_HEADERS = {
    "content-type": "application/json; charset=utf-8",
    # Job state changes between polls and must never be served from a cache.
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
}


class ApiError(Exception):
    """An error in the contract's shape (contracts/api.md, "Errors"). ``message`` is safe to show."""

    def __init__(self, status: int, code: str, message: str, details: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = list(details or [])


def detail(path: str, issue: str) -> dict[str, str]:
    return {"path": path, "issue": issue[:500] or "invalid"}


def json_response(status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    merged = dict(_BASE_HEADERS)
    if headers:
        merged.update(headers)
    return {
        "statusCode": status,
        "headers": merged,
        # UTF-8, not ASCII escapes: formula strings contain characters such as "≈".
        "body": json.dumps(body, separators=(",", ":"), ensure_ascii=False, allow_nan=False),
    }


def error_response(status: int, code: str, message: str, request_id: str | None = None, details: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """``api.schema.json#/$defs/error_response``: ``{"error": {code, message, details[], request_id}}``."""
    return json_response(status, {"error": {"code": code, "message": message, "details": list(details or []), "request_id": request_id}})
