"""Small in-memory fakes for S3, Lambda, Bedrock, SSM and the clock.

They reproduce only the behaviour the service relies on, including the error
codes of S3 conditional writes (412 PreconditionFailed, 409
ConditionalRequestConflict) as documented at
https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from botocore.exceptions import ClientError

BUCKET = "test-data-bucket"


def client_error(code: str, operation: str, status: int = 400) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}, "ResponseMetadata": {"HTTPStatusCode": status}}, operation)


class FakeClock:
    def __init__(self, now: float = 1_794_668_400.0) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True


class FakeS3:
    """Objects with ETags and If-None-Match / If-Match semantics."""

    def __init__(self, *, missing_is_access_denied: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts: list[dict[str, Any]] = []
        self.missing_is_access_denied = missing_is_access_denied
        # Called just before a put is evaluated: lets a test interleave a
        # concurrent writer between a read and the following write.
        self.before_put: list[Callable[[str], None]] = []
        self.fail_puts_with: list[ClientError] = []
        self.bodies: list[_Body] = []

    @staticmethod
    def _etag(data: bytes) -> str:
        return '"' + hashlib.md5(data).hexdigest() + '"'  # noqa: S324 - mirrors S3's ETag, not a security use

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str | None = None, IfNoneMatch: str | None = None, IfMatch: str | None = None) -> dict[str, Any]:
        assert Bucket == BUCKET
        hooks, self.before_put = self.before_put, []
        for hook in hooks:
            hook(Key)
        self.puts.append({"Key": Key, "IfNoneMatch": IfNoneMatch, "IfMatch": IfMatch})
        if self.fail_puts_with:
            raise self.fail_puts_with.pop(0)
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
        if Key not in self.objects:
            if self.missing_is_access_denied:
                raise client_error("AccessDenied", "GetObject", 403)
            raise client_error("NoSuchKey", "GetObject", 404)
        body = _Body(self.objects[Key])
        self.bodies.append(body)
        return {"Body": body, "ETag": self._etag(self.objects[Key])}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, MaxKeys: int = 1000, ContinuationToken: str | None = None) -> dict[str, Any]:
        assert Bucket == BUCKET
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        offset = int(ContinuationToken or 0)
        page = keys[offset:offset + MaxKeys]
        truncated = offset + MaxKeys < len(keys)
        return {"Contents": [{"Key": key} for key in page], "KeyCount": len(page), "IsTruncated": truncated,
                **({"NextContinuationToken": str(offset + MaxKeys)} if truncated else {})}

    # helpers for assertions
    def json(self, key: str) -> dict[str, Any]:
        return json.loads(self.objects[key])

    def keys(self, prefix: str = "") -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix))

    def unconditional_puts(self) -> list[dict[str, Any]]:
        return [put for put in self.puts if put["IfNoneMatch"] is None and put["IfMatch"] is None]


class FakeLambda:
    def __init__(self) -> None:
        self.invocations: list[dict[str, Any]] = []
        self.status_code = 202
        self.error: Exception | None = None
        self.on_invoke: Callable[[dict[str, Any]], None] | None = None

    def invoke(self, *, FunctionName: str, InvocationType: str, Payload: bytes) -> dict[str, Any]:
        record = {"FunctionName": FunctionName, "InvocationType": InvocationType, "Payload": json.loads(Payload)}
        self.invocations.append(record)
        if self.on_invoke is not None:
            self.on_invoke(record)
        if self.error is not None:
            raise self.error
        return {"StatusCode": self.status_code}


class FakeBedrock:
    """Returns scripted Converse responses; an Exception in the script is raised."""

    def __init__(self, script: list[Any] | None = None, *, repeat_last: bool = False) -> None:
        self.script = list(script or [])
        self.repeat_last = repeat_last
        self.calls: list[dict[str, Any]] = []
        self.on_call: Callable[[int], None] | None = None

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(copy.deepcopy(kwargs))
        if self.on_call is not None:
            self.on_call(len(self.calls))
        if not self.script:
            raise AssertionError("FakeBedrock: no scripted response left")
        item = self.script[0] if (self.repeat_last and len(self.script) == 1) else self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return copy.deepcopy(item)


def tool_use_response(name: str, arguments: Any, tool_use_id: str = "tooluse_1", text: str | None = None) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if text:
        content.append({"text": text})
    content.append({"toolUse": {"toolUseId": tool_use_id, "name": name, "input": arguments}})
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": "tool_use",
        "usage": {"inputTokens": 700, "outputTokens": 60, "totalTokens": 760},
        "metrics": {"latencyMs": 900},
        "ResponseMetadata": {"RequestId": "req-tool"},
    }


def final_response(text: str = '{"highlights": []}', stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}] if text else []}},
        "stopReason": stop_reason,
        "usage": {"inputTokens": 900, "outputTokens": 80, "totalTokens": 980},
        "metrics": {"latencyMs": 1100},
        "ResponseMetadata": {"RequestId": "req-final"},
    }


class FakeSSM:
    def __init__(self, value: str) -> None:
        self.value = value
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None

    def get_parameter(self, *, Name: str, WithDecryption: bool) -> dict[str, Any]:
        self.calls.append({"Name": Name, "WithDecryption": WithDecryption})
        if self.error is not None:
            raise self.error
        return {"Parameter": {"Name": Name, "Type": "SecureString", "Value": self.value}}


class FakeContext:
    def __init__(self, request_id: str = "lambda-req-1", remaining_ms: int = 160_000) -> None:
        self.aws_request_id = request_id
        self.function_name = "test-worker"
        self.function_version = "$LATEST"
        self.memory_limit_in_mb = 512
        self._remaining_ms = remaining_ms

    def get_remaining_time_in_millis(self) -> int:
        return self._remaining_ms


# ---------------------------------------------------------------------------
# Wiring helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = REPO_ROOT / "contracts"
PROCESSED = REPO_ROOT / "data" / "processed"
REAL_DATA_FILES = ("holdings.json", "instruments.json", "market_data.json", "controversies.json", "sources.json")
REAL_DATA_PRESENT = all((PROCESSED / name).exists() for name in REAL_DATA_FILES)
REAL_DATA_REASON = "data/processed/{holdings,instruments,market_data,controversies,sources}.json are not present (git-ignored)"
REAL_DATA_SOURCES = {"prices": "starter_prices_daily", "fx_usdcad": "starter_fx_usdcad"}

IDEMPOTENCY_KEY = "0b6f0c9e-5a7e-4c0e-9a55-1f2d3c4b5a61"
NVDA_REQUEST = {
    "instrument_id": "NVDA", "target_direct_weight": 0.25, "funding": "CASH",
    "original_words": "Everyone is talking about Nvidia. I want it to be 25% of my portfolio.",
}


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def scenario(persona_id: str) -> dict[str, Any]:
    return load_json(CONTRACTS / "scenarios" / f"{persona_id}.json")


def api_fixture(name: str) -> dict[str, Any]:
    return load_json(CONTRACTS / "fixtures" / "api" / f"{name}.json")


def _dump(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8")


def snapshot_contents(universe: str | None = "robert_synthetic_universe") -> dict[str, bytes]:
    """Snapshot files (relative name -> bytes), manifest included.

    ``universe`` names a SYNTHETIC contract universe (invented numbers, checkable by hand);
    ``None`` builds the snapshot from the real, git-ignored ``data/processed`` files.
    """
    from backend.common.data import DATA_FILES, PERSONA_IDS, build_manifest

    if universe is None:
        # The real snapshot is built by the same code the deploy step uses (scripts/build_snapshot.py).
        import importlib.util

        spec = importlib.util.spec_from_file_location("byb_build_snapshot", REPO_ROOT / "scripts" / "build_snapshot.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.build(PROCESSED, CONTRACTS / "scenarios")[1]
    else:
        document = load_json(CONTRACTS / "fixtures" / "engine" / f"{universe}.json")
        data = {name: document[name] for name in DATA_FILES}
        sources = {}
    contents = {f"{name}.json": _dump(data[name]) for name in DATA_FILES}
    for persona_id in PERSONA_IDS:
        contents[f"scenarios/{persona_id}.json"] = _dump(scenario(persona_id))
    manifest = build_manifest(data["market_data"]["valuation_date"], contents, sources)
    contents["manifest.json"] = _dump(manifest)
    return contents


def install_snapshot(s3: "FakeS3", universe: str | None = "robert_synthetic_universe") -> str:
    """Put a snapshot under ``snapshots/<id>/`` the way the upload script would. Returns the id."""
    contents = snapshot_contents(universe)
    snapshot_id = json.loads(contents["manifest.json"])["snapshot_id"]
    for name, data in contents.items():
        s3.objects[f"snapshots/{snapshot_id}/{name}"] = data
    return snapshot_id


def event(route: str, body: Any = None, *, path: dict[str, str] | None = None, headers: dict[str, str] | None = None, raw: str | None = None,
          request_id: str = "api-req-1") -> dict[str, Any]:
    """An API Gateway HTTP API (payload 2.0) event. Header names arrive lower-cased, as API Gateway sends them."""
    document: dict[str, Any] = {
        "version": "2.0",
        "routeKey": route,
        "headers": {name.lower(): value for name, value in (headers or {}).items()},
        "requestContext": {"requestId": request_id},
        "pathParameters": dict(path or {}),
        "isBase64Encoded": False,
    }
    if raw is not None or body is not None:
        document["body"] = raw if raw is not None else json.dumps(body)
    return document


def create_body(persona_id: str = "robert", policy_id: str = "pol-robert-demo", policy_version: int = 1, request: dict[str, Any] | None = None,
                parent: str | None = None) -> dict[str, Any]:
    return {"persona_id": persona_id, "policy_id": policy_id, "policy_version": policy_version,
            "request": dict(NVDA_REQUEST if request is None else request), "parent_investigation_id": parent}


def post_event(body: Any = None, *, headers: dict[str, str] | None = None, raw: str | None = None, key: str | None = IDEMPOTENCY_KEY) -> dict[str, Any]:
    merged = {"Idempotency-Key": key} if key is not None else {}
    merged.update(headers or {})
    return event("POST /investigations", create_body() if body is None and raw is None else body, headers=merged, raw=raw)


def get_event(job_id: str) -> dict[str, Any]:
    return event("GET /investigations/{id}", path={"id": job_id}, request_id="api-req-2")


def body_of(response: dict[str, Any]) -> dict[str, Any]:
    return json.loads(response["body"])


def confirm_body(persona_id: str = "robert", rules: list[dict[str, Any]] | None = None, **changes: Any) -> dict[str, Any]:
    """The scenario's offered rules, confirmed unchanged (contracts/fixtures/api/confirm_robert_v1.json)."""
    document = scenario(persona_id)
    offered = document["scenario_rules"] if rules is None else rules
    body = {
        "persona_id": persona_id, "policy_id": None, "base_version": None, "objectives": document["objectives"],
        "confirmations": [{"rule": rule, "threshold": rule["threshold"]} for rule in offered],
        "withdraw_rule_ids": [], "change_note": None,
    }
    body.update(changes)
    return body


def build_interpreter(bedrock: "FakeBedrock", clock: FakeClock, **options: Any):
    """The interpreter wired the way ``backend.api.handler._build_interpreter`` wires it, on the fake Bedrock."""
    from backend.agents.bedrock_client import BedrockConverse
    from backend.agents.interpreter import Interpreter

    counter = iter(range(1, 10_000))
    model = BedrockConverse(bedrock, "test-model", clock, max_attempts=2, base_delay_seconds=0.5, max_delay_seconds=1.0,
                            min_call_budget_seconds=13.0, rng=lambda: 1.0)
    return Interpreter(model, clock, new_id=lambda: hashlib.sha256(f"int-{next(counter)}".encode()).hexdigest()[:32], call_budget_seconds=13.0, **options)


def build_api(s3: FakeS3, lambda_client: FakeLambda, clock: FakeClock, *, deadline_seconds: int = 150, snapshot_id: str | None = None,
              ids: list[str] | None = None, bedrock: "FakeBedrock | None" = None):
    from backend.api.handler import Api
    from backend.common.config import ApiConfig
    from backend.common.data import S3SnapshotSource, SnapshotLoader
    from backend.common.jobs import JobStore
    from backend.common.policies import PolicyStore

    snapshot_id = snapshot_id or install_snapshot(s3)
    config = ApiConfig(data_bucket=BUCKET, worker_function_name="test-worker", job_deadline_seconds=deadline_seconds,
                       snapshot_id=snapshot_id, model_id="test-model")
    queue = list(ids or [])
    counter = iter(range(1, 10_000))
    return Api(
        store=JobStore(s3, BUCKET, clock, can_list=True),
        policies=PolicyStore(s3, BUCKET, can_list=True),
        snapshots=SnapshotLoader(S3SnapshotSource(s3, BUCKET, snapshot_id), snapshot_id),
        lambda_client=lambda_client,
        config=config,
        clock=clock,
        interpreter=build_interpreter(bedrock, clock) if bedrock is not None else None,
        # Deterministic and distinct in their first characters, like the uuid4 hex used in production.
        new_id=lambda: queue.pop(0) if queue else hashlib.sha256(str(next(counter)).encode()).hexdigest()[:32],
    )


def build_worker(s3: FakeS3, bedrock: FakeBedrock, clock: FakeClock, *, max_tool_rounds: int = 6, max_tool_calls: int = 16, snapshot_id: str | None = None,
                 registry_factory=None):
    from backend.agents.bedrock_client import BedrockConverse
    from backend.agents.tools import build_investigation_registry
    from backend.common.config import WorkerConfig
    from backend.common.data import S3SnapshotSource, SnapshotLoader
    from backend.common.jobs import JobStore
    from backend.common.policies import PolicyStore
    from backend.worker.investigation import InvestigationWorker

    snapshot_id = snapshot_id or install_snapshot(s3)
    config = WorkerConfig(data_bucket=BUCKET, model_id="test-model", max_tool_rounds=max_tool_rounds, max_tool_calls=max_tool_calls, max_tokens=1024,
                          code_artifact="test", snapshot_id=snapshot_id)
    return InvestigationWorker(
        store=JobStore(s3, BUCKET, clock, can_list=False),
        model=BedrockConverse(bedrock, "test-model", clock, rng=lambda: 1.0),
        snapshots=SnapshotLoader(S3SnapshotSource(s3, BUCKET, snapshot_id), snapshot_id),
        policies=PolicyStore(s3, BUCKET, can_list=False),
        config=config,
        clock=clock,
        registry_factory=registry_factory or build_investigation_registry,
    )


class Service:
    """API + worker + fakes wired together, driven only through the two Lambda handlers."""

    def __init__(self, universe: str | None = "robert_synthetic_universe", bedrock_script: list[Any] | None = None, **worker_options: Any) -> None:
        self.s3 = FakeS3()
        self.lambda_client = FakeLambda()
        self.clock = FakeClock()
        self.bedrock = FakeBedrock(bedrock_script if bedrock_script is not None else [final_response(EMPTY_ANSWER)], repeat_last=bedrock_script is None)
        self.snapshot_id = install_snapshot(self.s3, universe)
        self.api = build_api(self.s3, self.lambda_client, self.clock, snapshot_id=self.snapshot_id, bedrock=self.bedrock)
        self.worker = build_worker(self.s3, self.bedrock, self.clock, snapshot_id=self.snapshot_id, **worker_options)
        self._context = 0

    def call(self, route: str, body: Any = None, *, path: dict[str, str] | None = None, key: str | None = None, raw: str | None = None) -> tuple[int, dict[str, Any]]:
        headers = {"Idempotency-Key": key} if key is not None else {}
        response = self.api.handle(event(route, body, path=path, headers=headers, raw=raw), FakeContext("api-lambda"))
        assert response["headers"]["cache-control"] == "no-store"
        return response["statusCode"], body_of(response)

    def run_worker(self, job_id: str) -> dict[str, Any]:
        """Deliver the queued event to the worker, as Lambda's asynchronous invocation would."""
        self._context += 1
        return self.worker.handle({"job_id": job_id}, FakeContext(f"lambda-req-{self._context}"))

    def confirm(self, persona_id: str = "robert", **changes: Any) -> dict[str, Any]:
        status, body = self.call("POST /rules/confirm", confirm_body(persona_id, **changes))
        assert status == 201, body
        return body["policy"]

    def investigate(self, policy: dict[str, Any], request: dict[str, Any] | None = None, *, key: str = IDEMPOTENCY_KEY, run: bool = True) -> dict[str, Any]:
        status, accepted = self.call("POST /investigations", create_body(policy["persona_id"], policy["policy_id"], policy["version"], request), key=key)
        assert status == 202, accepted
        if run:
            self.run_worker(accepted["id"])
        return self.get(accepted["id"])

    def get(self, job_id: str) -> dict[str, Any]:
        status, body = self.call("GET /investigations/{id}", path={"id": job_id})
        assert status == 200, body
        return body


EMPTY_ANSWER = '{"highlights": []}'


def engine_data(universe: str | None = "robert_synthetic_universe") -> dict[str, Any]:
    """The same data the service reads, for running the engine directly in a comparison."""
    contents = snapshot_contents(universe)
    data = {name: json.loads(contents[f"{name}.json"]) for name in ("instruments", "holdings", "market_data", "controversies")}
    data["data_sources"] = json.loads(contents["manifest.json"])["data_sources"] or None
    return data


def engine_direct(universe: str | None, persona_id: str, policy: dict[str, Any] | None, request: dict[str, Any], draft_rules: Any = None) -> dict[str, Any]:
    """``backend.engine.check_rules`` called directly: the reference every service result is compared with."""
    from backend import engine

    data = engine_data(universe)
    return engine.check_rules(scenario(persona_id)["portfolio"], policy, request, data["instruments"], data["holdings"], data["market_data"],
                              data["controversies"], draft_rules=draft_rules, data_sources=data["data_sources"])


def model_answer(*statements: tuple[str, list[str]]) -> str:
    """Model-written sentences (the format the service once accepted). The service must return none of them."""
    return json.dumps({"statements": [{"text": text, "evidence_ids": ids} for text, ids in statements]})


def highlights(*items: Any) -> str:
    """The only thing a model can contribute: selections. An evidence id stands for a well-formed item."""
    return json.dumps({"highlights": [{"template": "HIGHLIGHT_VALUE", "evidence_id": item} if isinstance(item, str) else item for item in items]})
