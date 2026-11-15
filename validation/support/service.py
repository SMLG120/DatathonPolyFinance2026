"""Harness that drives the service through its real Lambda entry points with fake AWS clients.

``boto3.client`` is replaced by a factory returning the validator's fakes, the system clock by a manual clock,
and each handler module is reloaded so that its cached singletons are rebuilt on the fakes. The handlers under
test are the deployed ones:

    backend.api.handler.handler        (HTTP API, payload format 2.0)
    backend.api.authorizer.handler     (Lambda authorizer, simple responses)
    backend.worker.handler.handler     (asynchronous worker)

Because only entry points, environment variables and the AWS API are used, the same harness is meant to drive the
release candidate. Data files the release candidate may read from S3 are served by base name from the local
real data (``data/processed``) and the contract scenarios (``contracts/scenarios``): see ``_seed_lookup``.
"""

from __future__ import annotations

import importlib
import io
import json
from pathlib import Path
from typing import Any, Optional

import boto3

from . import fakes

REPO_ROOT = Path(__file__).resolve().parents[2]
BUCKET = "bucket"
ACCESS_CODE = "validator-access-code-0123456789"  # a made-up value for the fake SSM; never a real code
PARAMETER_NAME = "/before-you-buy/access-code"
MODEL_ID = "us.anthropic.claude-sonnet-5-5"


class SeededS3(fakes.FakeS3):
    """FakeS3 that can also serve read-only data snapshots by file name (for the release candidate)."""

    def __init__(self, serve_data: bool) -> None:
        super().__init__()
        self.serve_data = serve_data
        self.seed_hits: list[str] = []

    def _seed_lookup(self, key: str) -> Optional[bytes]:
        name = key.rsplit("/", 1)[-1]
        for folder in (REPO_ROOT / "data" / "processed", REPO_ROOT / "contracts" / "scenarios"):
            candidate = folder / name
            if name.endswith(".json") and candidate.is_file():
                return candidate.read_bytes()
        return None

    def get_object(self, **kwargs: Any) -> dict:
        slot = (kwargs["Bucket"], kwargs["Key"])
        if self.serve_data and slot not in self.objects and not kwargs["Key"].startswith(("jobs/", "results/", "traces/", "policies/")):
            data = self._seed_lookup(kwargs["Key"])
            if data is not None:
                self._maybe_fail("get_object", kwargs)
                self.seed_hits.append(kwargs["Key"])
                return {"Body": io.BytesIO(data), "ETag": '"seed"'}
        return super().get_object(**kwargs)


class Stack:
    def __init__(self, monkeypatch, *, bedrock_script: Optional[list] = None, access_code: Any = ACCESS_CODE,
                 ssm_error: Optional[Exception] = None, serve_data: bool = True, env: Optional[dict] = None) -> None:
        self.s3 = SeededS3(serve_data)
        self.lambda_ = fakes.FakeLambda()
        self.ssm = fakes.FakeSSM(access_code, ssm_error)
        self.bedrock = fakes.FakeBedrock(bedrock_script if bedrock_script is not None else [fakes.text_turn("No calculation was requested.")], repeat_last=bedrock_script is None)
        self.clock = fakes.ManualClock()
        self.log = io.StringIO()
        self.created_clients: list[str] = []

        settings = {
            "DATA_BUCKET": BUCKET, "WORKER_FUNCTION_NAME": "validator-worker", "BEDROCK_MODEL_ID": MODEL_ID,
            "ACCESS_CODE_PARAMETER_NAME": PARAMETER_NAME, "ACCESS_CODE_CACHE_SECONDS": "60", "LOG_LEVEL": "INFO",
            "AWS_DEFAULT_REGION": "us-east-1", "AWS_EC2_METADATA_DISABLED": "true",
        }
        settings.update(env or {})
        for name, value in settings.items():
            monkeypatch.setenv(name, value)
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

        def client(service_name: str, *args: Any, **kwargs: Any) -> Any:
            self.created_clients.append(service_name)
            table = {"s3": self.s3, "lambda": self.lambda_, "ssm": self.ssm, "bedrock-runtime": self.bedrock}
            if service_name not in table:
                raise AssertionError(f"the service asked for an AWS client the validator has no fake for: {service_name}")
            return table[service_name]

        def no_resource(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("boto3.resource is not faked by the validation harness")

        monkeypatch.setattr(boto3, "client", client)
        monkeypatch.setattr(boto3, "resource", no_resource)

        import backend.common.clock as clock_module
        import backend.common.log as log_module

        monkeypatch.setattr(clock_module, "SystemClock", lambda: self.clock)
        real_configure = log_module.configure
        monkeypatch.setattr(log_module, "configure", lambda level="INFO", stream=None: real_configure(level, self.log))
        real_configure("INFO", self.log)
        monkeypatch.setattr(log_module, "_context", {}, raising=False)

        self.api_module = importlib.reload(importlib.import_module("backend.api.handler"))
        self.worker_module = importlib.reload(importlib.import_module("backend.worker.handler"))
        self.authorizer_module = importlib.reload(importlib.import_module("backend.api.authorizer"))
        self._request_number = 0

    # ------------------------------------------------------------------ HTTP

    def http(self, method: str, route: str, *, path: Optional[dict] = None, body: Any = None, headers: Optional[dict] = None,
             raw_body: Optional[str] = None, base64_encoded: bool = False) -> "Response":
        self._request_number += 1
        request_id = f"req-{self._request_number}"
        raw_path = route
        for name, value in (path or {}).items():
            raw_path = raw_path.replace("{" + name + "}", str(value))
        event = {
            "version": "2.0", "routeKey": f"{method} {route}", "rawPath": raw_path,
            "headers": {"content-type": "application/json", **{k.lower(): v for k, v in (headers or {}).items()}},
            "pathParameters": path or {}, "requestContext": {"requestId": request_id, "http": {"method": method}},
            "isBase64Encoded": base64_encoded,
        }
        if raw_body is not None:
            event["body"] = raw_body
        elif body is not None:
            event["body"] = json.dumps(body)
        raw = self.api_module.handler(event, fakes.LambdaContext(request_id))
        return Response(raw)

    # ------------------------------------------------------------------ worker / authorizer

    def run_worker(self, job_id: Any, request_id: str = "lambda-req-1", remaining_ms: Optional[int] = 160_000, event: Any = None) -> Any:
        payload = event if event is not None else {"job_id": job_id}
        return self.worker_module.handler(payload, fakes.LambdaContext(request_id, remaining_ms))

    def dispatched_job_ids(self) -> list[str]:
        out = []
        for call in self.lambda_.invocations:
            payload = call.get("Payload")
            payload = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
            out.append(json.loads(payload).get("job_id"))
        return out

    def authorize(self, header: Any = None, *, identity_source: Any = "__from_header__", route: str = "POST /investigations") -> Any:
        event: dict[str, Any] = {"version": "2.0", "type": "REQUEST", "routeKey": route, "requestContext": {"requestId": "auth-req-1"}, "headers": {}}
        if header is not None:
            event["headers"]["authorization"] = header
        if identity_source == "__from_header__":
            if header is not None:
                event["identitySource"] = [header]
        elif identity_source is not None:
            event["identitySource"] = identity_source
        return self.authorizer_module.handler(event, fakes.LambdaContext("auth-lambda-1"))

    # ------------------------------------------------------------------ logs and storage

    def log_lines(self) -> list[dict]:
        return [json.loads(line) for line in self.log.getvalue().splitlines() if line.strip()]

    def log_text(self) -> str:
        return self.log.getvalue()

    def stored_text(self) -> str:
        return "\n".join(f"{key}\n{value.decode('utf-8', 'replace')}" for (_, key), value in sorted(self.s3.objects.items()))


class Response:
    def __init__(self, raw: dict) -> None:
        self.raw = raw
        self.status = raw.get("statusCode")
        self.headers = {k.lower(): v for k, v in (raw.get("headers") or {}).items()}
        self.text = raw.get("body") or ""
        try:
            self.json = json.loads(self.text) if self.text else None
        except ValueError:
            self.json = None

    @property
    def error_code(self) -> Optional[str]:
        return ((self.json or {}).get("error") or {}).get("code") if isinstance(self.json, dict) else None

    def __repr__(self) -> str:
        return f"<Response {self.status} {self.text[:300]}>"


# --------------------------------------------------------------------------- wire shapes

def phase1_body(instrument: str = "NVDA", weight: float = 0.25, persona: str = "robert", question: Optional[str] = None, **extra: Any) -> dict:
    """The provisional body accepted by commit d36e41f (backend/api/handler.py, parse_create_request)."""
    body: dict[str, Any] = {"persona_id": persona, "purchase": {"instrument_id": instrument, "target_direct_weight": weight}}
    if question is not None:
        body["question"] = question
    body.update(extra)
    return body


def contract_body(instrument: Optional[str] = "NVDA", weight: Optional[float] = 0.25, persona: str = "robert", policy_id: str = "pol-robert-demo",
                  policy_version: int = 1, words: Optional[str] = None, parent: Optional[str] = None) -> dict:
    """contracts/api.md section 6 (api.schema.json#/$defs/investigation_create_request)."""
    return {"persona_id": persona, "policy_id": policy_id, "policy_version": policy_version,
            "request": {"instrument_id": instrument, "target_direct_weight": weight, "funding": "CASH", "original_words": words},
            "parent_investigation_id": parent}


def investigation_id(response: Response) -> Optional[str]:
    body = response.json or {}
    return body.get("id") or body.get("investigation_id")
