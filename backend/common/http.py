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
    """An error with a stable machine-readable code that is safe to show."""

    def __init__(self, status: int, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def json_response(status: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    merged = dict(_BASE_HEADERS)
    if headers:
        merged.update(headers)
    return {
        "statusCode": status,
        "headers": merged,
        "body": json.dumps(body, separators=(",", ":"), allow_nan=False),
    }


def error_response(status: int, code: str, message: str, request_id: str | None = None, **details: Any) -> dict[str, Any]:
    """Body shape: ``{"error": {"code", "message", "request_id", ...}}``."""
    error: dict[str, Any] = {"code": code, "message": message}
    if request_id:
        error["request_id"] = request_id
    error.update({k: v for k, v in details.items() if v is not None})
    return json_response(status, {"error": error})
