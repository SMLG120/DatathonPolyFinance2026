"""Lambda authorizer for the HTTP API (payload format 2.0, simple responses).

Handler string: ``backend.api.authorizer.handler``.

It compares the bearer token of the ``Authorization`` header with the access
code stored in SSM Parameter Store (SecureString). This is demo-grade access
control (one shared code, see LEAD_DECISIONS D8), not user identity.

* The comparison is constant-time, on SHA-256 digests so that neither the
  length nor a prefix of the stored code leaks through timing.
* The stored code is cached in memory for a short time to keep SSM calls low.
* Fail closed: if the code cannot be read or is implausibly short, the
  function raises, API Gateway answers 500 and nothing is authorized.
* Neither the token nor the stored code is ever logged or returned.

CORS preflight requests never reach this function: API Gateway answers
OPTIONS itself when CORS is configured on the API.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from backend.common import log
from backend.common.config import AuthorizerConfig, ConfigurationError

MIN_ACCESS_CODE_LENGTH = 16
MAX_TOKEN_LENGTH = 512


class AccessCodeAuthorizer:
    def __init__(self, ssm: Any, config: AuthorizerConfig, clock: Any) -> None:
        self._ssm = ssm
        self._config = config
        self._clock = clock
        self._cached_digest: bytes | None = None
        self._cached_at = 0.0

    def _expected_digest(self) -> bytes:
        now = self._clock.time()
        if self._cached_digest is not None and now - self._cached_at < self._config.cache_ttl_seconds:
            return self._cached_digest
        response = self._ssm.get_parameter(Name=self._config.parameter_name, WithDecryption=True)
        code = response["Parameter"]["Value"]
        if not isinstance(code, str) or len(code) < MIN_ACCESS_CODE_LENGTH:
            raise ConfigurationError("the stored access code is shorter than the minimum length")
        # Only the digest is kept in memory between invocations.
        self._cached_digest = hashlib.sha256(code.encode("utf-8")).digest()
        self._cached_at = now
        return self._cached_digest

    @staticmethod
    def _bearer_token(event: dict[str, Any]) -> str | None:
        sources = event.get("identitySource")
        header = sources[0] if isinstance(sources, list) and sources else (event.get("headers") or {}).get("authorization")
        if not isinstance(header, str):
            return None
        scheme, _, token = header.strip().partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token or len(token) > MAX_TOKEN_LENGTH:
            return None
        return token

    def authorize(self, event: dict[str, Any]) -> dict[str, Any]:
        route = event.get("routeKey")
        token = self._bearer_token(event)
        if token is None:
            log.info("authorizer_decision", authorized=False, reason="missing_or_malformed_bearer_token", route=route)
            return {"isAuthorized": False}
        expected = self._expected_digest()
        presented = hashlib.sha256(token.encode("utf-8")).digest()
        authorized = hmac.compare_digest(presented, expected)
        log.info("authorizer_decision", authorized=authorized, reason="match" if authorized else "mismatch", route=route)
        return {"isAuthorized": authorized}


_authorizer: AccessCodeAuthorizer | None = None


def _build_authorizer() -> AccessCodeAuthorizer:
    import boto3
    from botocore.config import Config

    from backend.common.clock import SystemClock

    ssm = boto3.client(
        "ssm",
        config=Config(retries={"total_max_attempts": 2, "mode": "standard"}, connect_timeout=2, read_timeout=3),
    )
    return AccessCodeAuthorizer(ssm, AuthorizerConfig.from_env(), SystemClock())


def _get_authorizer() -> AccessCodeAuthorizer:
    global _authorizer
    if _authorizer is None:
        log.configure(os.environ.get("LOG_LEVEL", "INFO"))
        _authorizer = _build_authorizer()
    return _authorizer


# Inside Lambda, create the SSM client during the init phase. The access code
# itself is still read on the first request, never at import time.
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    _get_authorizer()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    log.bind(component="authorizer", request_id=(event.get("requestContext") or {}).get("requestId"))
    return _get_authorizer().authorize(event)
