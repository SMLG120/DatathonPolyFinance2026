"""Configuration read from environment variables set by the SAM template.

There is no ``.env`` file and no secret here: the only secret in the system is
the access code, which lives in SSM Parameter Store and is read by the
authorizer alone.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class ConfigurationError(Exception):
    """A required setting is missing or malformed. Never caused by a caller."""


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"environment variable {name} is not set")
    return value


def _integer(env: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"environment variable {name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"environment variable {name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class ApiConfig:
    data_bucket: str
    worker_function_name: str
    job_deadline_seconds: int = 150
    poll_interval_ms: int = 1500
    job_expiry_seconds: int = 86400
    snapshot_id: str = ""
    model_id: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ApiConfig":
        env = os.environ if env is None else env
        return cls(
            data_bucket=_required(env, "DATA_BUCKET"),
            worker_function_name=_required(env, "WORKER_FUNCTION_NAME"),
            job_deadline_seconds=_integer(env, "JOB_DEADLINE_SECONDS", 150, 10, 840),
            poll_interval_ms=_integer(env, "POLL_INTERVAL_MS", 1500, 500, 30000),
            job_expiry_seconds=_integer(env, "JOB_EXPIRY_SECONDS", 86400, 600, 259200),
            snapshot_id=_required(env, "DATA_SNAPSHOT_ID"),
            model_id=env.get("BEDROCK_MODEL_ID", "").strip() or None,
        )


@dataclass(frozen=True)
class WorkerConfig:
    data_bucket: str
    model_id: str
    max_tool_rounds: int = 6
    max_tool_calls: int = 16
    max_tokens: int = 4096
    code_artifact: str = "unknown"
    snapshot_id: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "WorkerConfig":
        env = os.environ if env is None else env
        return cls(
            data_bucket=_required(env, "DATA_BUCKET"),
            model_id=_required(env, "BEDROCK_MODEL_ID"),
            max_tool_rounds=_integer(env, "MAX_TOOL_ROUNDS", 6, 1, 20),
            max_tool_calls=_integer(env, "MAX_TOOL_CALLS", 16, 1, 64),
            max_tokens=_integer(env, "BEDROCK_MAX_TOKENS", 4096, 256, 16000),
            code_artifact=env.get("CODE_ARTIFACT", "unknown").strip() or "unknown",
            snapshot_id=_required(env, "DATA_SNAPSHOT_ID"),
        )


@dataclass(frozen=True)
class AuthorizerConfig:
    parameter_name: str
    cache_ttl_seconds: int = 30

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AuthorizerConfig":
        env = os.environ if env is None else env
        return cls(
            parameter_name=_required(env, "ACCESS_CODE_PARAMETER_NAME"),
            # Upper bound 300 s: this is the whole delay before a rotated code stops working (API Gateway caches nothing).
            cache_ttl_seconds=_integer(env, "ACCESS_CODE_CACHE_SECONDS", 30, 0, 300),
        )
