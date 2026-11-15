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

    def list_objects_v2(self, *, Bucket: str, Prefix: str, MaxKeys: int = 1000) -> dict[str, Any]:
        assert Bucket == BUCKET
        keys = sorted(key for key in self.objects if key.startswith(Prefix))[:MaxKeys]
        return {"Contents": [{"Key": key} for key in keys], "KeyCount": len(keys)}

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


def final_response(text: str = "The placeholder tool reports a direct weight of 0.25.", stop_reason: str = "end_turn") -> dict[str, Any]:
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

ROBERT_BODY = {
    "persona_id": "robert",
    "purchase": {"instrument_id": "NVDA", "target_direct_weight": 0.25},
    "idempotency_key": "robert-demo-key-0001",
}
CANONICAL_ARGS = {"instrument_id": "NVDA", "target_direct_weight": 0.25}


def post_event(body: Any = None, *, headers: dict[str, str] | None = None, raw: str | None = None) -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": "POST /investigations",
        "headers": dict(headers or {}),
        "requestContext": {"requestId": "api-req-1"},
        "body": raw if raw is not None else json.dumps(ROBERT_BODY if body is None else body),
        "isBase64Encoded": False,
    }


def get_event(job_id: str) -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": "GET /investigations/{id}",
        "headers": {},
        "requestContext": {"requestId": "api-req-2"},
        "pathParameters": {"id": job_id},
    }


def body_of(response: dict[str, Any]) -> dict[str, Any]:
    return json.loads(response["body"])


def build_api(s3: FakeS3, lambda_client: FakeLambda, clock: FakeClock, *, deadline_seconds: int = 150):
    from backend.api.handler import InvestigationApi
    from backend.common.config import ApiConfig
    from backend.common.jobs import JobStore

    config = ApiConfig(data_bucket=BUCKET, worker_function_name="test-worker", job_deadline_seconds=deadline_seconds)
    return InvestigationApi(store=JobStore(s3, BUCKET, clock, can_list=True), lambda_client=lambda_client, config=config, clock=clock)


def build_worker(s3: FakeS3, bedrock: FakeBedrock, clock: FakeClock, *, max_tool_rounds: int = 6, max_tool_calls: int = 16, registry=None):
    from backend.agents.bedrock_client import BedrockConverse
    from backend.agents.tools import build_phase1_registry
    from backend.common.config import WorkerConfig
    from backend.common.jobs import JobStore
    from backend.worker.investigation import InvestigationWorker

    config = WorkerConfig(data_bucket=BUCKET, model_id="test-model", max_tool_rounds=max_tool_rounds, max_tool_calls=max_tool_calls, max_tokens=1024, code_artifact="test")
    return InvestigationWorker(
        store=JobStore(s3, BUCKET, clock, can_list=False),
        model=BedrockConverse(bedrock, "test-model", clock, rng=lambda: 1.0),
        registry=registry or build_phase1_registry(),
        config=config,
        clock=clock,
    )
