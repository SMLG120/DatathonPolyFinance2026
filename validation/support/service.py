"""Harness that drives the service through its real Lambda entry points with fake AWS clients.

``boto3.client`` is replaced by a factory returning the validator's fakes, the system clock by a manual clock,
and each handler module is reloaded so that its cached singletons are rebuilt on the fakes. The handlers under
test are the deployed ones:

    backend.api.handler.handler        (HTTP API, payload format 2.0)
    backend.api.authorizer.handler     (Lambda authorizer, simple responses)
    backend.worker.handler.handler     (asynchronous worker)

Because only entry points, environment variables and the AWS API are used, the same harness is meant to drive the
release candidate. Data files the release candidate may read from S3 are served by base name from the local
real data (``data/processed``) and the contract scenarios (``contracts/scenarios``): see ``snapshot_contents``.
"""

from __future__ import annotations

import hashlib
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


DATA_FILE_NAMES = ("instruments", "holdings", "market_data", "controversies", "sources")
PERSONAS = ("robert", "mateo", "amira")
# Source-registry ids of the market data (the deployment's build script passes the same two ids).
DATA_SOURCES = {"prices": "starter_prices_daily", "fx_usdcad": "starter_fx_usdcad"}


def snapshot_contents() -> Optional[dict[str, bytes]]:
    """The files of a data snapshot (relative name -> bytes) from the local real data, or None when it is absent.

    Layout as documented in backend/common/data.py (module docstring): the five data files, scenarios/<persona>.json
    and manifest.json. The manifest is built HERE, by the validator, not by ``backend.common.data.build_manifest``:
    per-file SHA-256 and byte count, valuation date, market-data source ids, and the content-derived id
    ``snap-<valuation date>-<first 12 hex of sha256 over "name NUL sha256 NUL" for every file in name order>``.
    The id derivation is specified only by the code (``snapshot_id_for``); it was re-implemented from reading it.
    """
    contents: dict[str, bytes] = {}
    for name in DATA_FILE_NAMES:
        path = REPO_ROOT / "data" / "processed" / f"{name}.json"
        if not path.is_file():
            return None
        contents[f"{name}.json"] = path.read_bytes()
    for persona in PERSONAS:
        contents[f"scenarios/{persona}.json"] = (REPO_ROOT / "contracts" / "scenarios" / f"{persona}.json").read_bytes()
    return with_manifest(contents)


def with_manifest(contents: dict[str, bytes], valuation_date: Optional[str] = None) -> dict[str, bytes]:
    files = {name: data for name, data in contents.items() if name != "manifest.json"}
    if valuation_date is None:
        valuation_date = json.loads(files["market_data.json"])["valuation_date"]
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    digest = hashlib.sha256()
    for name in sorted(hashes):
        digest.update(name.encode("utf-8") + b"\x00" + hashes[name].encode("ascii") + b"\x00")
    manifest = {
        "schema_version": 1, "snapshot_id": f"snap-{valuation_date}-{digest.hexdigest()[:12]}", "valuation_date": valuation_date,
        "data_sources": dict(DATA_SOURCES),
        "files": {name: {"sha256": hashes[name], "bytes": len(files[name])} for name in sorted(files)},
    }
    return {**files, "manifest.json": json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")}


def snapshot_id_of(contents: dict[str, bytes]) -> str:
    return json.loads(contents["manifest.json"])["snapshot_id"]


class SeededS3(fakes.FakeS3):
    """FakeS3 that also serves one read-only data snapshot under ``snapshots/<snapshot id>/``."""

    def __init__(self, snapshot: Optional[dict[str, bytes]]) -> None:
        super().__init__()
        self.snapshot = dict(snapshot or {})
        self.snapshot_prefix = f"snapshots/{snapshot_id_of(self.snapshot)}/" if self.snapshot else None
        self.seed_hits: list[str] = []

    def get_object(self, **kwargs: Any) -> dict:
        key = kwargs["Key"]
        if key.startswith("snapshots/"):
            self._maybe_fail("get_object", kwargs)
            name = key[len(self.snapshot_prefix):] if self.snapshot_prefix and key.startswith(self.snapshot_prefix) else None
            if name not in self.snapshot:
                raise fakes.client_error("NoSuchKey", "GetObject", 404)
            self.seed_hits.append(key)
            return {"Body": io.BytesIO(self.snapshot[name]), "ETag": '"seed"'}
        return super().get_object(**kwargs)


class Stack:
    def __init__(self, monkeypatch, *, bedrock_script: Optional[list] = None, access_code: Any = ACCESS_CODE,
                 ssm_error: Optional[Exception] = None, snapshot: Any = "real", env: Optional[dict] = None) -> None:
        if snapshot == "real":
            snapshot = snapshot_contents()
            if snapshot is None:
                import pytest

                pytest.skip("the service needs a data snapshot and the git-ignored real data (data/processed/*.json) is not in this checkout")
        self.s3 = SeededS3(snapshot)
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
            "DATA_SNAPSHOT_ID": snapshot_id_of(snapshot) if snapshot else "snap-2026-11-12-000000000000",
            # As infra/template.yaml sets them on the API function (candidate deec650).
            "INTERPRETER_ENABLED": "true", "INTERPRETER_OUTPUT_LIMIT": "2048",
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
        self._configure_log = real_configure
        monkeypatch.setattr(log_module, "configure", lambda level="INFO", stream=None: real_configure(level, stream if stream is not None else self.log))
        real_configure("INFO", self.log)
        monkeypatch.setattr(log_module, "_context", {}, raising=False)

        self.api_module = importlib.reload(importlib.import_module("backend.api.handler"))
        self.worker_module = importlib.reload(importlib.import_module("backend.worker.handler"))
        self.authorizer_module = importlib.reload(importlib.import_module("backend.api.authorizer"))
        self._request_number = 0
        # Build the three applications now, through the modules' own factories (so on the fakes and the manual clock),
        # and keep them: several Stack objects can then coexist, each re-installing its own before a call.
        self._apps = (self.api_module._get_app(), self.worker_module._get_worker(), self.authorizer_module._get_authorizer())

    def _activate(self) -> None:
        self.api_module._app, self.worker_module._worker, self.authorizer_module._authorizer = self._apps
        self._configure_log("INFO", self.log)

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
        self._activate()
        raw = self.api_module.handler(event, fakes.LambdaContext(request_id))
        return Response(raw)

    # ------------------------------------------------------------------ worker / authorizer

    def run_worker(self, job_id: Any, request_id: str = "lambda-req-1", remaining_ms: Optional[int] = 160_000, event: Any = None) -> Any:
        payload = event if event is not None else {"job_id": job_id}
        self._activate()
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
        self._activate()
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
