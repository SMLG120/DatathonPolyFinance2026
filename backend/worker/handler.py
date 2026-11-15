"""Lambda entry point for the investigation worker.

Handler string: ``backend.worker.handler.handler``. Invoked asynchronously by
the API Lambda with ``{"job_id": "inv_..."}``.
"""

from __future__ import annotations

import os
from typing import Any

from backend.common import log

_worker = None


def _build_worker():
    import boto3
    from botocore.config import Config

    from backend.agents.bedrock_client import BedrockConverse
    from backend.agents.tools import build_phase1_registry
    from backend.common.clock import SystemClock
    from backend.common.config import WorkerConfig
    from backend.common.jobs import JobStore
    from backend.worker.investigation import InvestigationWorker

    config = WorkerConfig.from_env()
    clock = SystemClock()
    s3 = boto3.client(
        "s3",
        config=Config(retries={"total_max_attempts": 3, "mode": "standard"}, connect_timeout=3, read_timeout=10),
    )
    # One attempt per SDK call: retries, backoff and the deadline are handled
    # in BedrockConverse so each attempt is visible in the trace.
    bedrock = boto3.client(
        "bedrock-runtime",
        config=Config(retries={"total_max_attempts": 1, "mode": "standard"}, connect_timeout=5, read_timeout=60),
    )
    return InvestigationWorker(
        store=JobStore(s3, config.data_bucket, clock, can_list=False),
        model=BedrockConverse(bedrock, config.model_id, clock),
        registry=build_phase1_registry(),
        config=config,
        clock=clock,
    )


def _get_worker():
    global _worker
    if _worker is None:
        log.configure(os.environ.get("LOG_LEVEL", "INFO"))
        _worker = _build_worker()
    return _worker


# Inside Lambda, create the SDK clients during the init phase (outside the
# handler) so the first job does not pay for it. Anywhere else, stay lazy.
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    _get_worker()


def handler(event: Any, context: Any) -> dict[str, Any]:
    return _get_worker().handle(event, context)
