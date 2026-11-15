"""The real backend, in process: API Lambda handler + investigation worker + access-code authorizer, wired to
A2's in-memory fakes for S3, Lambda, Bedrock and SSM (``backend/tests/service/service_fakes.py``, imported
read-only), behind the transport seam of ``live_check.py``.

No socket, no AWS. The snapshot is built by ``scripts/build_snapshot.py`` from ``data/processed`` (``universe=None``)
or from a synthetic contract universe. What this cannot show is listed in README.md ("Unverifiable until a real
deployment"): API Gateway itself (routing, CORS, the 30 s cut, its own 401/403 bodies), IAM, real S3 and Lambda
asynchronous invocation, real time, and any model.

``bedrock_script`` is the list of Converse responses the one fake model plays, in call order, for the interpreter
(API) and the investigator (worker) alike; ``None`` repeats an empty investigator answer, which the interpreter
rejects (502 after its one retry).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_TESTS = REPO_ROOT / "backend" / "tests" / "service"
for _extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT, SERVICE_TESTS):
    if str(_extra) not in sys.path:
        sys.path.append(str(_extra))

import service_fakes as fakes  # noqa: E402  (A2's fakes; never edited from here)

import live_check as lc  # noqa: E402

ROUTES = (
    ("GET", "/portfolios/", "GET /portfolios/{persona_id}", "persona_id"),
    ("GET", "/investigations/", "GET /investigations/{id}", "id"),
)
EXACT = {("POST", "/rules/interpret"), ("POST", "/rules/confirm"), ("POST", "/check"), ("POST", "/investigations")}


class InProcessTransport:
    """``send(request) -> live_check.Response`` served by the real handlers.

    ``worker_after_polls``: the queued worker event is delivered just before that poll (1 = before the first
    poll), the way Lambda's asynchronous invocation finishes some time after the 202. ``None`` never delivers it.
    """

    def __init__(self, base_url: str, access_code: str, timeout: float = 30, max_requests: int = lc.DEFAULT_MAX_REQUESTS, *,
                 universe: Optional[str] = None, stored_access_code: Optional[str] = None, worker_after_polls: Optional[int] = 2,
                 bedrock_script: Optional[list] = None) -> None:
        from backend.api.authorizer import AccessCodeAuthorizer
        from backend.common.config import AuthorizerConfig

        self.base_url, self._code, self.max_requests = base_url, access_code, max_requests
        self.service = fakes.Service(universe, bedrock_script=bedrock_script)
        self.authorizer = AccessCodeAuthorizer(fakes.FakeSSM(stored_access_code if stored_access_code is not None else access_code),
                                               AuthorizerConfig(parameter_name="/byb/test/access-code", cache_ttl_seconds=300), self.service.clock)
        self.worker_after_polls = worker_after_polls
        self.sent = 0
        self.polls = 0
        self.delivered = 0
        self.log: list[tuple[str, str, int]] = []
        self.response_headers: list[dict] = []

    # the script's sleep and clock, so that server time and client time move together
    def sleep(self, seconds: float) -> None:
        self.service.clock.sleep(seconds)

    def clock(self) -> float:
        return self.service.clock.time()

    def _route(self, method: str, path: str) -> tuple[Optional[str], dict]:
        if (method, path) in EXACT:
            return f"{method} {path}", {}
        if method == "POST" and path.startswith("/investigations/") and path.endswith("/challenge"):
            job_id = path[len("/investigations/"):-len("/challenge")]
            if job_id and "/" not in job_id:
                return "POST /investigations/{id}/challenge", {"id": job_id}
        for wanted, prefix, route, parameter in ROUTES:
            rest = path[len(prefix):]
            if method == wanted and path.startswith(prefix) and rest and "/" not in rest:
                return route, {parameter: rest}
        return None, {}

    def deliver_worker_events(self) -> None:
        pending = self.service.lambda_client.invocations[self.delivered:]
        for record in pending:
            self.delivered += 1
            self.service.worker.handle(record["Payload"], fakes.FakeContext(f"worker-{self.delivered}"))

    def send(self, request: dict) -> lc.Response:
        if self.sent >= self.max_requests:
            raise lc.CouldNotRun(f"request budget of {self.max_requests} exhausted")
        self.sent += 1
        method, path = request["method"], request["path"]
        route, parameters = self._route(method, path)
        headers = dict(request["headers"], Authorization=f"Bearer {self._code}")  # added here only, as HttpTransport does
        event = fakes.event(route or "$default", request["body"], path=parameters, headers=headers, request_id=f"req-{self.sent}")
        if route is None:  # API Gateway answers an unknown route itself
            self.log.append((method, path, 404))
            return lc.Response(404, {"message": "Not Found"})
        if not self.authorizer.authorize(dict(event, identitySource=[headers["Authorization"]]))["isAuthorized"]:
            self.log.append((method, path, 403))
            return lc.Response(403, {"message": "Forbidden"})  # API Gateway's own body for a denied simple response
        if route == "GET /investigations/{id}":
            self.polls += 1
            if self.worker_after_polls is not None and self.polls >= self.worker_after_polls:
                self.deliver_worker_events()
        reply = self.service.api.handle(event, fakes.FakeContext(f"api-{self.sent}"))
        self.response_headers.append(reply.get("headers") or {})
        text = reply.get("body") or ""
        self.log.append((method, path, reply["statusCode"]))
        return lc.Response(reply["statusCode"], json.loads(text) if text else None, text)
