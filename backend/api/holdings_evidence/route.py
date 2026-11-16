"""``POST /evidence/investigate`` — additive route; reads the snapshot and stored policies, writes nothing.

Request (every key required except the policy pair; unknown keys are refused, so a caller cannot send its own figures)::

    {"persona_id": "robert", "fund_id": "XIU.TO" | null, "question": "...", "policy_id": "pol-..." | null, "policy_version": 1 | null}

Registration (``backend/api/handler.py``, in ``Api.__init__``)::

    from backend.api.holdings_evidence.route import ROUTE_KEY, evidence_route
    self._routes[ROUTE_KEY] = evidence_route(self)

The route runs inside ``Api.handle``, so authentication (the Lambda authorizer), CORS and the error shape are the
existing ones.

Model wording is OFF in this release (``MODEL_WORDING_ENABLED``): the project shows no model-written text
(``backend/agents/explain.py``; test ``wk01f``), so every answer is the server's own deterministic wording and the
route makes no Bedrock call. The guarded explainer stays in ``wording.py``, tested, for a later decision by the lead.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from backend.api.holdings_evidence.wording import ModelExplainer
from backend.api.holdings_evidence.service import UnknownFund, investigate
from backend.common import log
from backend.common.http import ApiError, detail, json_response

ROUTE_KEY = "POST /evidence/investigate"
MAX_QUESTION_CHARS = 500
_PERSONA_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")
_FUND_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]{0,31}")
_KEYS = frozenset({"persona_id", "fund_id", "question", "policy_id", "policy_version"})
_MESSAGE = "The request body does not match the evidence investigation contract."
# Release decision: no model-written text is shown. While this is False the route never builds a model client.
MODEL_WORDING_ENABLED = False


def _invalid(path: str, issue: str) -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", _MESSAGE, [detail(path, issue)])


def validate(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise _invalid("", "must be a JSON object")
    extra = sorted(set(body) - _KEYS)
    if extra:
        raise _invalid(str(extra[0])[:40], "is not accepted; figures are calculated by the service, not supplied")
    persona_id, fund_id, question = body.get("persona_id"), body.get("fund_id"), body.get("question")
    if not isinstance(persona_id, str) or _PERSONA_RE.fullmatch(persona_id) is None:
        raise _invalid("persona_id", "is required")
    if fund_id is not None and (not isinstance(fund_id, str) or _FUND_RE.fullmatch(fund_id) is None):
        raise _invalid("fund_id", "must be a fund identifier or null")
    if not isinstance(question, str) or not question.strip():
        raise _invalid("question", "is required")
    if len(question) > MAX_QUESTION_CHARS:
        raise _invalid("question", f"is longer than {MAX_QUESTION_CHARS} characters")
    policy_id, version = body.get("policy_id"), body.get("policy_version")
    if (policy_id is None) != (version is None):
        raise _invalid("policy_version", "policy_id and policy_version are both null or both set")
    return {"persona_id": persona_id, "fund_id": fund_id, "question": question.strip(), "policy_id": policy_id, "policy_version": version}


class EvidenceRoute:
    def __init__(self, *, read_body: Callable[[dict], dict], snapshot: Callable[[], Any], policies: Any,
                 explainer: Callable[[], Any] | None = None) -> None:
        self._read_body, self._snapshot, self._policies, self._explainer = read_body, snapshot, policies, explainer

    def __call__(self, event: dict[str, Any], request_id: str | None) -> dict[str, Any]:
        request = validate(self._read_body(event))
        snapshot = self._snapshot()
        scenario = snapshot.scenario(request["persona_id"])
        if scenario is None:
            raise ApiError(404, "NOT_FOUND", "The service has no record of this persona.", [detail("persona_id", "unknown persona")])
        policy = None
        if request["policy_id"] is not None:
            policy = self._policies.get(request["policy_id"], request["policy_version"])
            if policy is None or policy.get("persona_id") != request["persona_id"]:
                raise ApiError(404, "NOT_FOUND", "The service has no record of this policy version.", [detail("policy_version", "unknown policy version")])
        explainer = None
        if self._explainer is not None:
            try:
                explainer = self._explainer()
            except Exception as error:  # noqa: BLE001 - the model is optional: without it the server's wording is used
                log.warning("evidence_explainer_unavailable", error_type=type(error).__name__)
        try:
            result = investigate(snapshot=snapshot, scenario=scenario, policy=policy, fund_id=request["fund_id"],
                                 question=request["question"], explainer=explainer)
        except UnknownFund as error:
            raise ApiError(404, "NOT_FOUND", "The service has no record of this fund.", [detail("fund_id", "unknown fund")]) from error
        log.info("evidence_investigated", persona_id=request["persona_id"], fund_id=request["fund_id"], topic=result["question"]["topic"],
                 status=result["status"], explanation_source=result["explanation_source"], model_status=result["model_status"])
        return json_response(200, result)


def _lazy_explainer(config: Any) -> Callable[[], Any] | None:
    """The model client is built on first use, with the interpreter's timeouts, and only if the interpreter switch is on."""
    if not MODEL_WORDING_ENABLED or not getattr(config, "interpreter_enabled", False) or not getattr(config, "model_id", None):
        return None
    cache: list[Any] = []

    def build() -> Any:
        if not cache:
            import boto3
            from botocore.config import Config

            client = boto3.client("bedrock-runtime", config=Config(retries={"total_max_attempts": 1, "mode": "standard"},
                                                                    connect_timeout=1, read_timeout=12))
            cache.append(ModelExplainer(client, config.model_id))
        return cache[0]

    return build


def evidence_route(api: Any, explainer: Callable[[], Any] | None = None) -> EvidenceRoute:
    """The route bound to an ``Api`` (its snapshot loader, policy store and configuration)."""
    from backend.api.handler import read_json_body

    return EvidenceRoute(read_body=read_json_body, snapshot=api._snapshot, policies=api._policies,
                         explainer=explainer if explainer is not None else _lazy_explainer(api._config))
