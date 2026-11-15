#!/usr/bin/env python3
"""Local full-stack harness: the real backend handlers behind an emulated API Gateway HTTP API.

Three loopback listeners (127.0.0.1 only, nothing else is ever contacted):

    API      (--api-port,     default 4184)  what the browser calls: exactly the 7 routes of contracts/api.md
    site     (--site-port,    default 4185)  the static live-mode build of the frontend (the CORS allowed origin)
    control  (--control-port, default 4186)  test-only switches and read-outs; never called by the page

What is real: ``backend.api.handler.Api``, ``backend.api.authorizer.AccessCodeAuthorizer``,
``backend.worker.investigation.InvestigationWorker``, ``backend.engine``, the job / policy stores, the
snapshot loader, and the data (``data/processed`` through ``scripts/build_snapshot.py``'s ``build``).

What is fake: S3 (in memory, with If-None-Match / If-Match), SSM (holds the runtime test code), Lambda
(``invoke`` answers 202 and a thread delivers the event to the worker afterwards), Bedrock (scripted,
see ``FakeBedrock``), and API Gateway itself (this file). See README.md for what that cannot prove.

Emulated API Gateway behaviour (infra/template.yaml):
* payload format 2.0 events; header names lower-cased;
* only the 7 routes exist; anything else is 404 ``{"message":"Not Found"}`` (there is no $default route);
* Lambda authorizer with simple responses, identity source = the Authorization header, no caching:
  header missing -> 401 ``{"message":"Unauthorized"}`` without invoking the authorizer; ``isAuthorized: false``
  -> 403 ``{"message":"Forbidden"}``; an authorizer exception -> 500 ``{"message":"Internal Server Error"}``;
* CORS: preflight is answered by the gateway without the authorizer (204; allow-origin only for the allowed
  origin; methods GET, POST, OPTIONS; headers authorization, content-type, idempotency-key; max-age 600);
  the allow-origin header is added to every response for the allowed origin;
* throttling is injected on demand (429 ``{"message":"Too Many Requests"}``), not rate-computed.

Run through ``run.sh``; standalone:

    BYB_LOCAL_ACCESS_CODE=<any 16+ chars> uv run --offline --no-project --python 3.14 --with boto3 --with jsonschema \
        python acceptance/fullstack/local_api.py
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
import time
import uuid
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from botocore.exceptions import ClientError  # noqa: E402

from backend import engine  # noqa: E402
from backend.agents.bedrock_client import BedrockConverse  # noqa: E402
from backend.api.authorizer import AccessCodeAuthorizer  # noqa: E402
from backend.api.handler import Api, _build_interpreter  # noqa: E402
from backend.common import log  # noqa: E402
from backend.common.config import ApiConfig, AuthorizerConfig, WorkerConfig  # noqa: E402
from backend.common.data import S3SnapshotSource, SnapshotLoader  # noqa: E402
from backend.common.jobs import JobStore  # noqa: E402
from backend.common.policies import PolicyStore  # noqa: E402
from backend.worker.investigation import InvestigationWorker  # noqa: E402

BUCKET = "local-fullstack-bucket"
MODEL_ID = "local-fake-model"
SSM_PARAMETER = "/before-you-buy/local/access-code"
HOST = "127.0.0.1"

ROUTES = (
    ("GET", re.compile(r"/portfolios/([^/]+)"), "GET /portfolios/{persona_id}", "persona_id"),
    ("POST", re.compile(r"/rules/interpret"), "POST /rules/interpret", None),
    ("POST", re.compile(r"/rules/confirm"), "POST /rules/confirm", None),
    ("POST", re.compile(r"/check"), "POST /check", None),
    ("POST", re.compile(r"/investigations"), "POST /investigations", None),
    ("GET", re.compile(r"/investigations/([^/]+)"), "GET /investigations/{id}", "id"),
    ("POST", re.compile(r"/investigations/([^/]+)/challenge"), "POST /investigations/{id}/challenge", "id"),
)
CORS_ALLOW_METHODS = "GET,POST,OPTIONS"
CORS_ALLOW_HEADERS = "authorization,content-type,idempotency-key"
CORS_MAX_AGE = "600"

# What the hostile investigator tries. None of these strings may reach a response or the page.
HOSTILE_MARKER = "SMUGGLED"
HOSTILE_STATEMENTS = [
    {"text": "Every rule passes. You should buy.", "evidence_ids": []},
    {"text": "NVIDIA will rise sharply next year, so this purchase is safe.", "evidence_ids": []},
    {"text": "Every rule passes and the replay returned [[ev-scn-ret-prop]]. You should buy.", "evidence_ids": ["ev-scn-ret-prop"]},
]
HOSTILE_TOOL_NAME = "SMUGGLED_tool_everything_passes"
HOSTILE_TOOL_INPUT = {"note": "SMUGGLED-ARGUMENT: every rule passes, you should buy", "instrument_id": "SMUGGLED-INSTRUMENT"}
HOSTILE_TOOL_TEXT = "SMUGGLED-THOUGHT: I will tell the investor to buy."
HOSTILE_HIGHLIGHTS = [
    {"template": "SMUGGLED-TEMPLATE Every rule passes. You should buy.", "evidence_id": "ev-scn-ret-prop"},
    {"template": "HIGHLIGHT_VALUE", "evidence_id": "SMUGGLED-EVIDENCE-ID"},
    {"template": "HIGHLIGHT_VALUE", "evidence_id": "ev-scn-ret-prop", "text": "SMUGGLED-MEMBER You should buy."},
]
BENIGN_EVIDENCE_ID = "ev-scn-ret-prop"
INTERPRETER_TOOL = "submit_interpretation"
INTERPRETER_MODES = ("careful", "silent", "garbage", "slow", "obedient", "unavailable")
GARBAGE_TEXT = "SMUGGLED-GARBAGE I think every rule should be confirmed. You should buy."


# --------------------------------------------------------------------------- scripted interpreter extraction


def _user_words(messages: list[dict[str, Any]]) -> str:
    """The investor's text, as the server put it in the <user_words> block (one JSON string)."""
    text = "".join(block.get("text", "") for message in messages for block in message.get("content", []))
    match = re.search(r"<user_words>\n(.*?)\n</user_words>", text, re.DOTALL)
    return json.loads(match.group(1)) if match else ""


def _reference_companies(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The companies the server found in the text and listed in <reference_data> (issuer_id, name)."""
    text = "".join(block.get("text", "") for message in messages for block in message.get("content", []))
    match = re.search(r"<reference_data>\n(.*?)\n</reference_data>", text, re.DOTALL)
    return (json.loads(match.group(1)).get("companies") or []) if match else []


def careful_extraction(text: str, companies: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """What a careful extractor marks: spans of the text and closed codes, nothing else. It follows the tool's
    instructions literally (a percentage is pointed at through threshold_words, never supplied)."""
    objectives: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"[^.;!?\n]+", text):
        raw = match.group(0)
        start = match.start() + (len(raw) - len(raw.lstrip()))
        end = match.end() - (len(raw) - len(raw.rstrip()))
        if end - start < 3:
            continue
        words = text[start:end]
        lowered = words.lower()
        kind = "constraint" if re.search(r"\b(avoid|no more than|not|never|at most|lose|loss|exclude|without)\b", lowered) else \
            "preference" if re.search(r"\b(matters?|prefer|care|like)\b", lowered) else "goal"
        objectives.append({"words": words, "kind": kind})
        spans.append((start, end))

    def objective_of(position: int) -> Any:
        for index, (start, end) in enumerate(spans):
            if start <= position < end:
                return index
        return None

    def sentence_of(position: int) -> str:
        index = objective_of(position)
        return text[spans[index][0]:spans[index][1]] if index is not None else ""

    rules: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    for match in re.finditer(r"(?i)\b(no more than|at most|a maximum of|max(?:imum)?)\s+\d+(?:[.,]\d+)?\s*(?:%|percent)[^.;!?\n]*?\b(?:any (?:one|single) (?:company|issuer|stock)|a single (?:company|issuer|stock)|one (?:company|issuer|stock))", text):
        rules.append({"words": match.group(0), "rule_type": "max_issuer_exposure", "issuer_id": None, "threshold_words": match.group(0), "objective": objective_of(match.start())})
    # "No more than 5% in NVIDIA": a cap on one company the server listed in its reference data.
    for start, end in spans:
        sentence = text[start:end]
        if not re.search(r"(?i)\b(no more than|at most|a maximum of|max(?:imum)?)\s+\d+(?:[.,]\d+)?\s*(?:%|percent)", sentence) or any(rule["words"] in sentence for rule in rules):
            continue
        for company in companies or []:
            first_word = re.split(r"[^A-Za-z0-9]+", company["name"].strip())[0]
            if len(first_word) >= 3 and re.search(rf"(?i)\b{re.escape(first_word)}\b", sentence):
                rules.append({"words": sentence, "rule_type": "max_issuer_exposure", "issuer_id": company["issuer_id"], "threshold_words": sentence, "objective": objective_of(start)})
                break
    for match in re.finditer(r"(?i)\b(?:lose|loss(?:es)?|drop|fall|lower)\b", text):
        sentence = sentence_of(match.start())
        if sentence and re.search(r"\d\s*(%|percent)", sentence) and not any(rule["words"] == sentence for rule in rules) \
                and not any(rule["words"] in sentence for rule in rules):
            rules.append({"words": sentence, "rule_type": "scenario_loss_budget", "threshold_words": sentence, "objective": objective_of(match.start())})
    for match in re.finditer(r"(?i)\bcompan(?:y|ies)\s+(?:involved in|with|that have|having)\s+[^.;!?\n]*?controvers(?:y|ies)", text):
        rules.append({"words": match.group(0), "rule_type": "controversy_exclusion", "threshold_words": None, "objective": objective_of(match.start())})
    for match in re.finditer(r"(?i)\b(oil|petroleum|fossil fuels?|fossil)\b", text):
        ambiguous.append({"words": match.group(0), "topic": "EXCLUSION_DEFINITION", "sector": "Energy", "objective": objective_of(match.start())})
    for match in re.finditer(r"(?i)\b(diversified|well diversified|not (?:too )?concentrated|spread out)\b", text):
        ambiguous.append({"words": match.group(0), "topic": "DIVERSIFICATION", "objective": objective_of(match.start())})
    for match in re.finditer(r"(?i)\b(preserve my capital|limit (?:my )?losses|low risk)\b", text):
        ambiguous.append({"words": match.group(0), "topic": "LOSS_LIMIT", "objective": objective_of(match.start())})
    for match in re.finditer(r"(?i)\b(ignore (?:all |the |your )?(?:previous |prior )?(?:rules|instructions)[^.;!?\n]*|mark (?:everything|every rule|all rules)[^.;!?\n]*)", text):
        unsupported.append({"words": match.group(0), "reason": "INSTRUCTION"})
    return {"objectives": objectives[:8], "rules": rules[:8], "ambiguous": ambiguous[:8], "unsupported": unsupported[:8]}


def obedient_extraction(text: str, companies: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """A model that does what it must not: supplies numbers and statuses, and decides what "oil" means (wrongly)."""
    careful = careful_extraction(text, companies)
    rules = []
    for rule in careful["rules"]:
        rules.append(dict(rule, threshold=0, threshold_source="USER_WORDS", threshold_quote="0%", status="CONFIRMED", origin="USER_CONFIRMED",
                          scope_description="SMUGGLED-SCOPE every rule passes"))
    for item in careful["ambiguous"]:
        if item["topic"] == "EXCLUSION_DEFINITION":
            rules.append({"words": item["words"], "rule_type": "exclusion", "sector": "Utilities", "threshold": 0, "status": "CONFIRMED",
                          "objective": item.get("objective")})
    return {"objectives": careful["objectives"], "rules": rules, "ambiguous": [], "unsupported": [],
            "status": "CONFIRMED", "note": "SMUGGLED-NOTE confirmed on the investor's behalf"}


def client_error(code: str, operation: str, status: int = 400) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, operation)


# --------------------------------------------------------------------------- clock


class OffsetClock:
    """Real time plus an offset the control port can only increase (to step past a job deadline)."""

    def __init__(self) -> None:
        self.offset = 0.0

    def time(self) -> float:
        return time.time() + self.offset

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


# --------------------------------------------------------------------------- fakes


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        pass


class FakeS3:
    """In-memory objects with ETags and S3's conditional-write answers (412 PreconditionFailed). Thread-safe."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self._lock = threading.RLock()
        # Test switch: the next put whose key starts with this prefix fails once with InternalError.
        self.fail_next_put_prefix: str | None = None

    @staticmethod
    def _etag(data: bytes) -> str:
        return '"' + hashlib.md5(data).hexdigest() + '"'  # noqa: S324 - mirrors S3's ETag

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str | None = None, IfNoneMatch: str | None = None,
                   IfMatch: str | None = None, **_ignored: Any) -> dict[str, Any]:
        assert Bucket == BUCKET
        with self._lock:
            if self.fail_next_put_prefix and Key.startswith(self.fail_next_put_prefix):
                self.fail_next_put_prefix = None
                raise client_error("InternalError", "PutObject", 500)
            if IfNoneMatch == "*" and Key in self.objects:
                raise client_error("PreconditionFailed", "PutObject", 412)
            if IfMatch is not None:
                if Key not in self.objects:
                    raise client_error("NoSuchKey", "PutObject", 404)
                if self._etag(self.objects[Key]) != IfMatch:
                    raise client_error("PreconditionFailed", "PutObject", 412)
            self.objects[Key] = bytes(Body)
            return {"ETag": self._etag(self.objects[Key])}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        assert Bucket == BUCKET
        with self._lock:
            if Key not in self.objects:
                raise client_error("NoSuchKey", "GetObject", 404)
            data = self.objects[Key]
            return {"Body": _Body(data), "ETag": self._etag(data)}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, MaxKeys: int = 1000) -> dict[str, Any]:
        assert Bucket == BUCKET
        with self._lock:
            keys = sorted(key for key in self.objects if key.startswith(Prefix))[:MaxKeys]
            return {"Contents": [{"Key": key} for key in keys], "KeyCount": len(keys)}


class FakeSSM:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_parameter(self, *, Name: str, WithDecryption: bool) -> dict[str, Any]:
        assert Name == SSM_PARAMETER and WithDecryption is True
        return {"Parameter": {"Name": Name, "Type": "SecureString", "Value": self._value}}


class FakeBedrock:
    """Scripted Converse for both model users. A call that offers the ``submit_interpretation`` tool is the
    interpreter's (API Lambda); any other call is the investigator's (worker).

    Investigator, ``settings['bedrock_mode']``:

    fallback  every call raises AccessDeniedException (not retryable) -> the worker's DETERMINISTIC_FALLBACK
    benign    one round of tool calls, then ``{"highlights": [...]}`` selecting one evidence id a tool result showed
    hostile   a tool call with an invented name and smuggled arguments and prose, then the old prose format
              (``statements``) on the first job and smuggled highlight items on the next (alternating per final answer)

    Interpreter, ``settings['interpreter_mode']``:

    careful      a valid extraction of the investor's words (``careful_extraction``)
    silent       the tool called with four empty lists
    garbage      prose instead of the tool -> rejected twice -> 502 INTERPRETER_FAILED
    slow         the server's clock moves 21 s during the call -> 504 INTERPRETER_TIMEOUT
    obedient     numbers, statuses and the wrong sector supplied by the model (``obedient_extraction``)
    unavailable  AccessDeniedException -> 502
    """

    def __init__(self, settings: dict[str, Any], clock: "OffsetClock | None" = None) -> None:
        self._settings = settings
        self._clock = clock
        self.calls = 0
        self.interpreter_calls = 0
        self._hostile_finals = 0

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        tool_names = [tool.get("toolSpec", {}).get("name") for tool in (kwargs.get("toolConfig") or {}).get("tools", [])]
        if INTERPRETER_TOOL in tool_names:
            return self._interpreter(kwargs)
        delay = float(self._settings.get("bedrock_delay_s") or 0)
        if delay > 0:
            time.sleep(delay)
        mode = self._settings.get("bedrock_mode")
        if mode == "fallback":
            raise client_error("AccessDeniedException", "Converse", 403)
        messages = kwargs["messages"]
        tool_rounds = sum(1 for m in messages if m.get("role") == "user" and any("toolResult" in b for b in m.get("content", [])))
        tools = ["get_portfolio", "get_policy", "simulate_change", "get_holdings", "compute_exposure", "replay_period"]
        # One tool per round, so the job shows its steps one by one (as a model that calls tools in sequence does).
        rounds = tools if self._settings.get("bedrock_stepwise") else None
        if rounds is not None and tool_rounds < len(rounds):
            return self._tool_use([rounds[tool_rounds]], tool_rounds)
        if rounds is None and tool_rounds == 0:
            hostile = mode == "hostile"
            return self._tool_use(tools, 0, hostile=hostile)
        if mode == "hostile":
            self._hostile_finals += 1
            answer = {"statements": HOSTILE_STATEMENTS} if self._hostile_finals % 2 == 1 else {"highlights": HOSTILE_HIGHLIGHTS}
            if self._settings.get("hostile_answer") in ("statements", "highlights"):
                answer = {"statements": HOSTILE_STATEMENTS} if self._settings["hostile_answer"] == "statements" else {"highlights": HOSTILE_HIGHLIGHTS}
        else:
            # Select only an evidence id that a tool result really showed (the rule the server enforces).
            shown = BENIGN_EVIDENCE_ID in json.dumps(messages)
            answer = {"highlights": [{"template": "HIGHLIGHT_VALUE", "evidence_id": BENIGN_EVIDENCE_ID}] if shown else []}
        return self._final(json.dumps(answer))

    def _interpreter(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        self.interpreter_calls += 1
        mode = self._settings.get("interpreter_mode")
        text = _user_words(kwargs["messages"])
        companies = _reference_companies(kwargs["messages"])
        if mode == "unavailable":
            raise client_error("AccessDeniedException", "Converse", 403)
        if mode == "garbage":
            return self._final(GARBAGE_TEXT)
        if mode == "slow":
            if self._clock is not None:
                self._clock.offset += 21.0
            return self._interpretation(careful_extraction(text, companies))
        if mode == "silent":
            return self._interpretation({"objectives": [], "rules": [], "ambiguous": [], "unsupported": []})
        if mode == "obedient":
            return self._interpretation(obedient_extraction(text, companies))
        return self._interpretation(careful_extraction(text, companies))

    def _interpretation(self, extraction: dict[str, Any]) -> dict[str, Any]:
        return {
            "output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": f"interp-{self.calls}", "name": INTERPRETER_TOOL, "input": extraction}}]}},
            "stopReason": "tool_use",
            "usage": {"inputTokens": 700, "outputTokens": 60, "totalTokens": 760},
            "metrics": {"latencyMs": 1},
            "ResponseMetadata": {"RequestId": f"fake-interp-{self.calls}"},
        }

    def _final(self, text: str) -> dict[str, Any]:
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 900, "outputTokens": 80, "totalTokens": 980},
            "metrics": {"latencyMs": 1},
            "ResponseMetadata": {"RequestId": f"fake-final-{self.calls}"},
        }

    def _tool_use(self, names: list[str], round_index: int, hostile: bool = False) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"text": HOSTILE_TOOL_TEXT}] if hostile else []
        content += [{"toolUse": {"toolUseId": f"tool-{round_index}-{i}", "name": name, "input": {}}} for i, name in enumerate(names)]
        if hostile:  # an invented tool, and a real tool with invented arguments
            content.append({"toolUse": {"toolUseId": f"tool-{round_index}-x1", "name": HOSTILE_TOOL_NAME, "input": dict(HOSTILE_TOOL_INPUT)}})
            content.append({"toolUse": {"toolUseId": f"tool-{round_index}-x2", "name": "simulate_change", "input": dict(HOSTILE_TOOL_INPUT)}})
        return {
            "output": {"message": {"role": "assistant", "content": content}},
            "stopReason": "tool_use",
            "usage": {"inputTokens": 700, "outputTokens": 60, "totalTokens": 760},
            "metrics": {"latencyMs": 1},
            "ResponseMetadata": {"RequestId": f"fake-tool-{self.calls}"},
        }


class _FakeBoto3:
    """What ``backend.api.handler._build_interpreter`` asks of boto3: one bedrock-runtime client."""

    def __init__(self, bedrock: FakeBedrock) -> None:
        self._bedrock = bedrock

    def client(self, name: str, **_: Any) -> FakeBedrock:
        assert name == "bedrock-runtime", name
        return self._bedrock


class LambdaContext:
    def __init__(self, name: str, remaining_ms: int = 160_000) -> None:
        self.aws_request_id = f"{name}-{uuid.uuid4().hex[:12]}"
        self.function_name = name
        self.function_version = "$LATEST"
        self.memory_limit_in_mb = 512
        self._remaining_ms = remaining_ms

    def get_remaining_time_in_millis(self) -> int:
        return self._remaining_ms


class FakeLambda:
    """``invoke(InvocationType='Event')`` answers 202 at once; a thread delivers the event to the worker later."""

    def __init__(self, stack: "Stack") -> None:
        self._stack = stack
        self.invocations: list[dict[str, Any]] = []

    def invoke(self, *, FunctionName: str, InvocationType: str, Payload: bytes) -> dict[str, Any]:
        settings = self._stack.settings
        payload = json.loads(Payload)
        record = {"FunctionName": FunctionName, "InvocationType": InvocationType, "Payload": payload, "delivered": False,
                  "worker_outcome": None}
        self.invocations.append(record)
        if settings.get("invoke_error"):
            raise client_error("ServiceException", "Invoke", 500)
        if settings.get("worker_never_delivered"):
            return {"StatusCode": 202}
        delay = float(settings.get("worker_delay_s") or 0)

        def deliver() -> None:
            if delay > 0:
                time.sleep(delay)
            try:
                record["worker_outcome"] = self._stack.worker.handle(payload, LambdaContext("local-worker"))
            except Exception as error:  # noqa: BLE001 - an async invocation swallows the error (retries are 0 in the template)
                record["worker_outcome"] = {"outcome": "raised", "error_type": type(error).__name__, "error": str(error)[:300]}
            record["delivered"] = True

        threading.Thread(target=deliver, name="worker-delivery", daemon=True).start()
        return {"StatusCode": 202}


# --------------------------------------------------------------------------- the stack


def default_settings() -> dict[str, Any]:
    return {
        "bedrock_mode": os.environ.get("BYB_LOCAL_BEDROCK_MODE", "fallback"),
        "bedrock_delay_s": float(os.environ.get("BYB_LOCAL_BEDROCK_DELAY_S", "0")),
        "bedrock_stepwise": False,
        "hostile_answer": None,
        "interpreter_mode": os.environ.get("BYB_LOCAL_INTERPRETER_MODE", "careful"),
        "worker_delay_s": float(os.environ.get("BYB_LOCAL_WORKER_DELAY_S", "0")),
        "worker_never_delivered": os.environ.get("BYB_LOCAL_WORKER_NEVER", "") == "1",
        "invoke_error": False,
        "throttle_post_investigations": int(os.environ.get("BYB_LOCAL_THROTTLE_POST_INVESTIGATIONS", "0")),
        "throttle_all": 0,
        "gateway_errors_have_cors": os.environ.get("BYB_LOCAL_GATEWAY_ERRORS_CORS", "1") == "1",
        "job_deadline_seconds": 150,
    }


def build_real_snapshot() -> tuple[dict, dict[str, bytes]]:
    """(manifest, contents) from data/processed, by the deploy step's own builder (scripts/build_snapshot.py)."""
    spec = importlib.util.spec_from_file_location("byb_build_snapshot", REPO_ROOT / "scripts" / "build_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(REPO_ROOT / "data" / "processed", REPO_ROOT / "contracts" / "scenarios")


class Stack:
    def __init__(self, access_code: str, allowed_origin: str) -> None:
        self.allowed_origin = allowed_origin
        self.settings = default_settings()
        self.clock = OffsetClock()
        self.s3 = FakeS3()
        self.request_log: list[dict[str, Any]] = []
        self._log_lock = threading.Lock()
        self._expected_authorization = "Bearer " + access_code

        manifest, contents = build_real_snapshot()
        self.snapshot_id = manifest["snapshot_id"]
        for name, data in contents.items():
            self.s3.objects[f"snapshots/{self.snapshot_id}/{name}"] = data
        self._documents = {name: json.loads(contents[f"{name}.json"]) for name in ("instruments", "holdings", "market_data", "controversies")}
        self._scenarios = {p: json.loads(contents[f"scenarios/{p}.json"]) for p in ("robert", "mateo", "amira")}
        self._data_sources = manifest["data_sources"] or None

        self.lambda_client = FakeLambda(self)
        self.bedrock = FakeBedrock(self.settings, self.clock)
        self.authorizer = AccessCodeAuthorizer(FakeSSM(access_code), AuthorizerConfig(parameter_name=SSM_PARAMETER, cache_ttl_seconds=30), self.clock)
        self.worker = InvestigationWorker(
            store=JobStore(self.s3, BUCKET, self.clock, can_list=False),
            model=BedrockConverse(self.bedrock, MODEL_ID, self.clock),
            snapshots=SnapshotLoader(S3SnapshotSource(self.s3, BUCKET, self.snapshot_id), self.snapshot_id),
            policies=PolicyStore(self.s3, BUCKET, can_list=False),
            config=WorkerConfig(data_bucket=BUCKET, model_id=MODEL_ID, code_artifact="local-fullstack", snapshot_id=self.snapshot_id),
            clock=self.clock,
        )
        self._api_snapshots = SnapshotLoader(S3SnapshotSource(self.s3, BUCKET, self.snapshot_id), self.snapshot_id)
        self.api = self._build_api()

    def _build_api(self) -> Api:
        # The API function's environment, as infra/template.yaml sets it (INTERPRETER_ENABLED: "true"), read by the
        # backend's own ApiConfig.from_env; the interpreter is built by the handler's own _build_interpreter.
        env = {"DATA_BUCKET": BUCKET, "WORKER_FUNCTION_NAME": "local-worker", "JOB_DEADLINE_SECONDS": str(int(self.settings["job_deadline_seconds"])),
               "POLL_INTERVAL_MS": "1500", "DATA_SNAPSHOT_ID": self.snapshot_id, "BEDROCK_MODEL_ID": MODEL_ID, "INTERPRETER_ENABLED": "true"}
        config = ApiConfig.from_env(env)
        assert config.interpreter_enabled and config.snapshot_id == self.snapshot_id and config.model_id == MODEL_ID, config
        interpreter = _build_interpreter(_FakeBoto3(self.bedrock), lambda **_: None, config, self.clock)
        assert interpreter is not None
        return Api(interpreter=interpreter, store=JobStore(self.s3, BUCKET, self.clock, can_list=True), policies=PolicyStore(self.s3, BUCKET, can_list=True),
                   snapshots=self._api_snapshots, lambda_client=self.lambda_client, config=config, clock=self.clock)

    def apply_settings(self, changes: dict[str, Any]) -> None:
        unknown = sorted(set(changes) - set(self.settings))
        if unknown:
            raise ValueError(f"unknown settings: {unknown}")
        self.settings.update(changes)
        if "job_deadline_seconds" in changes:
            self.api = self._build_api()

    def reset(self) -> None:
        self.settings.clear()
        self.settings.update(default_settings())
        self.s3.fail_next_put_prefix = None
        # Everything a test stored (policies, jobs, results, traces, corrections); the snapshot stays.
        with self.s3._lock:
            for key in [key for key in self.s3.objects if not key.startswith("snapshots/")]:
                del self.s3.objects[key]
        self.lambda_client.invocations.clear()
        self.bedrock.calls = 0
        self.bedrock.interpreter_calls = 0
        self.bedrock._hostile_finals = 0
        self.api = self._build_api()
        with self._log_lock:
            self.request_log.clear()

    def record(self, entry: dict[str, Any]) -> None:
        with self._log_lock:
            entry["seq"] = len(self.request_log) + 1
            self.request_log.append(entry)

    def authorization_state(self, value: str | None) -> str:
        """Never the value itself: only whether it is the expected one."""
        if value is None:
            return "missing"
        return "expected" if value == self._expected_authorization else "other"

    def engine_check(self, body: dict[str, Any]) -> dict[str, Any]:
        """``backend.engine.check_rules`` called directly on the snapshot's documents: the reference for every API number."""
        data = self._documents
        return engine.check_rules(self._scenarios[body["persona_id"]]["portfolio"], body.get("policy"), body["purchase_request"], data["instruments"],
                                  data["holdings"], data["market_data"], data["controversies"], draft_rules=body.get("draft_rules"),
                                  data_sources=self._data_sources)


# --------------------------------------------------------------------------- emulated API Gateway


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "local-apigw"
    stack: Stack  # set on the class by serve()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - silence the default stderr access log
        pass

    # ---- helpers

    def _origin_allowed(self) -> bool:
        allowed = self.stack.allowed_origin
        origin = self.headers.get("Origin")
        return origin is not None and (allowed == "*" or origin == allowed)

    def _send(self, status: int, body: str | None, headers: dict[str, str], *, from_gateway: bool) -> None:
        payload = (body or "").encode("utf-8")
        self.send_response(status)
        merged = {name.lower(): value for name, value in headers.items()}
        if self._origin_allowed() and (not from_gateway or self.stack.settings["gateway_errors_have_cors"] or self.command == "OPTIONS"):
            merged["access-control-allow-origin"] = "*" if self.stack.allowed_origin == "*" else self.stack.allowed_origin
        merged["content-length"] = str(len(payload))
        for name, value in merged.items():
            self.send_header(name, value)
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def _gateway(self, status: int, message: str, entry: dict[str, Any]) -> None:
        entry.update(status=status, answered_by="gateway")
        self.stack.record(entry)
        self._send(status, json.dumps({"message": message}), {"content-type": "application/json"}, from_gateway=True)

    # ---- methods

    def do_OPTIONS(self) -> None:  # noqa: N802
        entry = self._entry()
        entry.update(status=204, answered_by="gateway-cors", access_control_request_headers=self.headers.get("Access-Control-Request-Headers"),
                     access_control_request_method=self.headers.get("Access-Control-Request-Method"))
        self.stack.record(entry)
        headers = {}
        if self._origin_allowed():
            headers = {"access-control-allow-methods": CORS_ALLOW_METHODS, "access-control-allow-headers": CORS_ALLOW_HEADERS,
                       "access-control-max-age": CORS_MAX_AGE}
        self._send(204, None, headers, from_gateway=True)

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def do_PUT(self) -> None:  # noqa: N802
        self._handle()

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle()

    def _entry(self) -> dict[str, Any]:
        return {
            "t": time.time(), "method": self.command, "path": self.path, "origin": self.headers.get("Origin"),
            "authorization": self.stack.authorization_state(self.headers.get("Authorization")),
            "idempotency_key": self.headers.get("Idempotency-Key"), "content_type": self.headers.get("Content-Type"),
            "cookie": self.headers.get("Cookie"), "query": self.path.partition("?")[2],
        }

    def _handle(self) -> None:
        stack = self.stack
        entry = self._entry()
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace") if length else None
        path, _, query = self.path.partition("?")

        route_key, parameters = None, {}
        for method, pattern, key, parameter in ROUTES:
            match = pattern.fullmatch(path)
            if method == self.command and match:
                route_key, parameters = key, ({parameter: match.group(1)} if parameter else {})
                break
        entry["route"] = route_key
        if route_key is None:
            return self._gateway(404, "Not Found", entry)

        settings = stack.settings
        if settings["throttle_all"] > 0:
            settings["throttle_all"] -= 1
            return self._gateway(429, "Too Many Requests", entry)
        if route_key == "POST /investigations" and settings["throttle_post_investigations"] > 0:
            settings["throttle_post_investigations"] -= 1
            return self._gateway(429, "Too Many Requests", entry)

        request_id = uuid.uuid4().hex[:16]
        headers = {name.lower(): value for name, value in self.headers.items()}
        context = {"accountId": "000000000000", "apiId": "local", "domainName": f"{HOST}", "requestId": request_id, "routeKey": route_key,
                   "stage": "$default", "timeEpoch": int(stack.clock.time() * 1000),
                   "http": {"method": self.command, "path": path, "protocol": "HTTP/1.1", "sourceIp": HOST, "userAgent": headers.get("user-agent", "")}}

        # Lambda authorizer (payload 2.0, simple response). The identity source is the Authorization header.
        authorization = headers.get("authorization")
        if not authorization:
            return self._gateway(401, "Unauthorized", entry)
        try:
            decision = stack.authorizer.authorize({
                "version": "2.0", "type": "REQUEST", "routeArn": f"arn:aws:execute-api:local:000000000000:local/$default/{self.command}{path}",
                "identitySource": [authorization], "routeKey": route_key, "rawPath": path, "rawQueryString": query, "headers": headers,
                "requestContext": context, "pathParameters": parameters,
            })
        except Exception:  # noqa: BLE001 - the authorizer fails closed; API Gateway answers 500
            return self._gateway(500, "Internal Server Error", entry)
        if decision.get("isAuthorized") is not True:
            return self._gateway(403, "Forbidden", entry)

        event: dict[str, Any] = {"version": "2.0", "routeKey": route_key, "rawPath": path, "rawQueryString": query, "headers": headers,
                                 "requestContext": context, "pathParameters": parameters, "isBase64Encoded": False}
        if raw is not None:
            event["body"] = raw
        reply = stack.api.handle(event, LambdaContext("local-api", 20_000))
        entry.update(status=reply["statusCode"], answered_by="lambda", request_id=request_id)
        stack.record(entry)
        self._send(reply["statusCode"], reply.get("body"), dict(reply.get("headers") or {}), from_gateway=False)


# --------------------------------------------------------------------------- control port (tests only)


class ControlHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    stack: Stack

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def _json(self, status: int, document: Any) -> None:
        payload = json.dumps(document).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        stack = self.stack
        if self.path == "/health":
            return self._json(200, {"ok": True, "snapshot_id": stack.snapshot_id, "allowed_origin": stack.allowed_origin})
        if self.path == "/log":
            return self._json(200, {"requests": stack.request_log})
        if self.path == "/state":
            return self._json(200, {
                "settings": stack.settings, "snapshot_id": stack.snapshot_id, "clock_offset_s": stack.clock.offset,
                "s3_keys": sorted(key for key in stack.s3.objects if not key.startswith("snapshots/")),
                "invocations": [{"job_id": r["Payload"].get("job_id"), "delivered": r["delivered"], "worker_outcome": r["worker_outcome"]}
                                for r in stack.lambda_client.invocations],
                "bedrock_calls": stack.bedrock.calls, "interpreter_calls": stack.bedrock.interpreter_calls,
            })
        self._json(404, {"error": "unknown control path"})

    def do_POST(self) -> None:  # noqa: N802
        stack = self.stack
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        try:
            if self.path == "/reset":
                stack.reset()
                return self._json(200, {"settings": stack.settings})
            if self.path == "/settings":
                stack.apply_settings(body)
                return self._json(200, {"settings": stack.settings})
            if self.path == "/advance-clock":
                stack.clock.offset += float(body["seconds"])
                return self._json(200, {"clock_offset_s": stack.clock.offset})
            if self.path == "/fail-next-put":
                stack.s3.fail_next_put_prefix = body["prefix"]
                return self._json(200, {"prefix": body["prefix"]})
            if self.path == "/engine-check":
                return self._json(200, stack.engine_check(body))
            if self.path == "/stored":
                data = stack.s3.objects.get(body["key"])
                return self._json(200, {"found": data is not None, "document": json.loads(data) if data is not None else None})
        except Exception as error:  # noqa: BLE001 - a test tool: report the problem to the test
            return self._json(400, {"error": f"{type(error).__name__}: {error}"})
        self._json(404, {"error": "unknown control path"})


class SiteHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve(server: ThreadingHTTPServer, name: str) -> None:
    threading.Thread(target=server.serve_forever, name=name, daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Before You Buy: local full-stack harness (loopback only, no AWS).")
    parser.add_argument("--api-port", type=int, default=4184)
    parser.add_argument("--site-port", type=int, default=4185)
    parser.add_argument("--control-port", type=int, default=4186)
    parser.add_argument("--site-dir", default=str(Path(__file__).resolve().parent / ".site"))
    parser.add_argument("--log-file", default=str(Path(__file__).resolve().parent / ".run" / "backend.log"))
    arguments = parser.parse_args()

    access_code = os.environ.get("BYB_LOCAL_ACCESS_CODE", "")
    if len(access_code) < 16:
        print("local_api.py: BYB_LOCAL_ACCESS_CODE must be set to a made-up value of at least 16 characters (run.sh generates one)", file=sys.stderr)
        return 2
    origin = os.environ.get("BYB_LOCAL_ALLOWED_ORIGIN", f"http://{HOST}:{arguments.site_port}")

    log_path = Path(arguments.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log.configure("INFO", log_path.open("a", encoding="utf-8", buffering=1))

    stack = Stack(access_code, origin)
    GatewayHandler.stack = stack
    ControlHandler.stack = stack
    ThreadingHTTPServer.daemon_threads = True
    api = ThreadingHTTPServer((HOST, arguments.api_port), GatewayHandler)
    control = ThreadingHTTPServer((HOST, arguments.control_port), ControlHandler)
    serve(api, "api")
    serve(control, "control")
    site_dir = Path(arguments.site_dir)
    if (site_dir / "index.html").exists():
        serve(ThreadingHTTPServer((HOST, arguments.site_port), partial(SiteHandler, directory=str(site_dir))), "site")
        site = f"http://{HOST}:{arguments.site_port}"
    else:
        site = f"(not served: {site_dir}/index.html is missing)"
    print(json.dumps({"ready": True, "api": f"http://{HOST}:{arguments.api_port}", "site": site, "control": f"http://{HOST}:{arguments.control_port}",
                      "allowed_origin": origin, "snapshot_id": stack.snapshot_id, "bedrock_mode": stack.settings["bedrock_mode"]}), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
