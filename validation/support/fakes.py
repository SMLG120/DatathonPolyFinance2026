"""The validator's own in-memory fakes for S3, Lambda, SSM and Bedrock, plus a manual clock.

Written from the AWS API behaviour the service relies on (conditional PutObject, asynchronous Invoke, GetParameter,
Converse). No real client is ever created and nothing here touches the network.
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any, Callable, Optional

from botocore.exceptions import ClientError, ReadTimeoutError


def client_error(code: str, operation: str = "Operation", status: int = 400) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": f"fake {code}"}, "ResponseMetadata": {"HTTPStatusCode": status}}, operation)


class ManualClock:
    """``time()`` only moves when a test or ``sleep`` moves it."""

    def __init__(self, start: float = 1_794_000_000.0) -> None:
        self.now = start
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += max(0.0, seconds)

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeS3:
    """Objects in a dict; PutObject honours If-None-Match: * and If-Match: <etag> as S3 does (412 on mismatch)."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.etags: dict[tuple[str, str], str] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail: dict[str, list] = {}          # operation -> queue of exceptions to raise (one per call)
        self.fail_when: Optional[Callable[[str, dict], Optional[Exception]]] = None
        self.unconditional_puts: list[str] = []
        self._version = 0

    # -- helpers for tests
    def json(self, key: str, bucket: str = "bucket") -> Any:
        return json.loads(self.objects[(bucket, key)])

    def keys(self, prefix: str = "") -> list[str]:
        return sorted(key for (_, key) in self.objects if key.startswith(prefix))

    def _maybe_fail(self, operation: str, kwargs: dict) -> None:
        self.calls.append((operation, {k: v for k, v in kwargs.items() if k != "Body"}))
        queue = self.fail.get(operation)
        if queue:
            raise queue.pop(0)
        if self.fail_when:
            error = self.fail_when(operation, kwargs)
            if error:
                raise error

    # -- S3 API subset
    def get_object(self, **kwargs: Any) -> dict:
        self._maybe_fail("get_object", kwargs)
        slot = (kwargs["Bucket"], kwargs["Key"])
        if slot not in self.objects:
            raise client_error("NoSuchKey", "GetObject", 404)
        return {"Body": io.BytesIO(self.objects[slot]), "ETag": self.etags[slot]}

    def put_object(self, **kwargs: Any) -> dict:
        self._maybe_fail("put_object", kwargs)
        slot = (kwargs["Bucket"], kwargs["Key"])
        if "IfNoneMatch" not in kwargs and "IfMatch" not in kwargs:
            self.unconditional_puts.append(kwargs["Key"])
        if kwargs.get("IfNoneMatch") == "*" and slot in self.objects:
            raise client_error("PreconditionFailed", "PutObject", 412)
        if "IfMatch" in kwargs and self.etags.get(slot) != kwargs["IfMatch"]:
            raise client_error("PreconditionFailed", "PutObject", 412)
        body = kwargs["Body"]
        self._version += 1
        self.objects[slot] = body if isinstance(body, bytes) else body.encode("utf-8")
        self.etags[slot] = '"' + hashlib.md5(self.objects[slot] + str(self._version).encode()).hexdigest() + '"'
        return {"ETag": self.etags[slot]}

    def list_objects_v2(self, **kwargs: Any) -> dict:
        self._maybe_fail("list_objects_v2", kwargs)
        found = [{"Key": key} for (bucket, key) in sorted(self.objects) if bucket == kwargs["Bucket"] and key.startswith(kwargs.get("Prefix", ""))]
        return {"Contents": found[: kwargs.get("MaxKeys", 1000)]} if found else {}


class FakeLambda:
    def __init__(self) -> None:
        self.invocations: list[dict] = []
        self.status_code = 202
        self.raise_error: Optional[Exception] = None

    def invoke(self, **kwargs: Any) -> dict:
        self.invocations.append(kwargs)
        if self.raise_error:
            raise self.raise_error
        return {"StatusCode": self.status_code}


class FakeSSM:
    def __init__(self, value: Any = None, error: Optional[Exception] = None) -> None:
        self.value = value
        self.error = error
        self.calls: list[dict] = []

    def get_parameter(self, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"Parameter": {"Name": kwargs["Name"], "Value": self.value, "Type": "SecureString"}}


def text_turn(text: str, stop: str = "end_turn") -> dict:
    return {"stopReason": stop, "output": {"message": {"role": "assistant", "content": [{"text": text}] if text is not None else []}},
            "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}, "metrics": {"latencyMs": 1}}


def tool_turn(*calls: tuple, text: Optional[str] = None) -> dict:
    """calls: (tool name, input) pairs or (tool name, input, tool_use_id)."""
    content: list[dict] = [{"text": text}] if text else []
    for index, call in enumerate(calls):
        name, arguments = call[0], call[1]
        tool_use_id = call[2] if len(call) > 2 else f"tu-{index}"
        content.append({"toolUse": {"toolUseId": tool_use_id, "name": name, "input": arguments}})
    return {"stopReason": "tool_use", "output": {"message": {"role": "assistant", "content": content}},
            "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}, "metrics": {"latencyMs": 1}}


def read_timeout() -> ReadTimeoutError:
    return ReadTimeoutError(endpoint_url="https://bedrock.invalid")


class FakeBedrock:
    """Plays a script: each entry is a Converse response dict, an exception to raise, or a callable(kwargs) -> either."""

    def __init__(self, script: list, repeat_last: bool = False) -> None:
        self.script = list(script)
        self.repeat_last = repeat_last
        self.requests: list[dict] = []

    def converse(self, **kwargs: Any) -> dict:
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        if not self.script:
            raise AssertionError("FakeBedrock: the service called Converse more often than the script allows")
        step = self.script[0] if (self.repeat_last and len(self.script) == 1) else self.script.pop(0)
        if callable(step):
            step = step(kwargs)
        if isinstance(step, BaseException):
            raise step
        return step


class LambdaContext:
    def __init__(self, request_id: str = "lambda-req-1", remaining_ms: Optional[int] = None) -> None:
        self.aws_request_id = request_id
        self.function_name = "validator-fake-function"
        self.function_version = "$LATEST"
        self.memory_limit_in_mb = "512"
        self._remaining_ms = remaining_ms
        if remaining_ms is not None:
            self.get_remaining_time_in_millis = lambda: self._remaining_ms
