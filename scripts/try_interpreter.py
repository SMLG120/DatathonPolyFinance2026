"""Try the rule interpreter on your own sentences, with the real Bedrock model, on a SYNTHETIC data snapshot.

Nothing is stored and no AWS resource of the stack is needed: only ``bedrock:InvokeModel`` (Converse) in us-east-1
with the credentials of your environment. The interpreter is built exactly as the API Lambda builds it
(``backend.api.handler._build_interpreter``: same timeouts, retries, 20 s budget).

From the repository root:

    uv run --no-project --with boto3 python scripts/try_interpreter.py "I want only environmental investments"
    uv run --no-project --with boto3 python scripts/try_interpreter.py --json "Only tech stocks" "Avoid Google"

Options: ``--universe`` (mateo_synthetic_universe | robert_synthetic_universe | synthetic_universe),
``--model`` (default: the stack's model id), ``--json`` (print the whole interpretation).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT, REPO_ROOT / "backend" / "tests" / "service"):
    sys.path.insert(0, str(extra))

DEFAULT_MODEL = "us.anthropic.claude-sonnet-5-5"


def load_snapshot(universe: str):
    from backend.common.data import FileSnapshotSource, SnapshotLoader
    from service_fakes import snapshot_contents  # the test suite's builder for synthetic snapshots

    directory = Path(tempfile.mkdtemp(prefix="byb-snapshot-"))
    for name, data in snapshot_contents(universe).items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return SnapshotLoader(FileSnapshotSource(directory)).load()


def summary(draft: dict) -> str:
    lines = []
    for objective in draft["objectives"]:
        lines.append(f"  objective  [{objective['kind']}] {objective['original_words']!r}")
    for rule in draft["proposed_rules"]:
        number = "no number" if rule["threshold"] is None else f"threshold {rule['threshold']} from {rule['threshold_quote']!r}"
        lines.append(f"  rule       {rule['rule_type']} {json.dumps(rule['parameters'])} ({number}) from {rule['original_words']!r}")
    for clarification in draft["clarifications"]:
        lines.append(f"  question   {clarification['question']}")
        for option in clarification["options"]:
            mark = "x" if not option["supported"] else ("+" if option["proposed_rule"] else "-")
            lines.append(f"      [{mark}] {option['option_id']}: {option['label']}")
    for item in draft["unsupported"]:
        lines.append(f"  unsupported {item['code']} {item['words']!r}: {item['reason']}")
    return "\n".join(lines) or "  (empty draft)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sentences", nargs="+")
    parser.add_argument("--universe", default="mateo_synthetic_universe")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--persona", default="mateo", choices=("robert", "mateo", "amira"))
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()

    import boto3
    from botocore.config import Config

    from backend.agents.interpreter import InterpreterFailed, InterpreterTimeout
    from backend.api.handler import _build_interpreter
    from backend.common import log
    from backend.common.clock import SystemClock
    from backend.common.config import ApiConfig

    log.configure("INFO", sys.stderr)  # outcome, attempts, lookup rounds and token usage go to stderr
    snapshot = load_snapshot(arguments.universe)
    config = ApiConfig(data_bucket="unused", worker_function_name="unused", model_id=arguments.model, interpreter_enabled=True)
    interpreter = _build_interpreter(boto3.session.Session(region_name="us-east-1"), Config, config, SystemClock())
    failures = 0
    for sentence in arguments.sentences:
        started = time.time()
        print(f"\n> {sentence}")
        try:
            draft = interpreter.interpret(text=sentence, persona_id=arguments.persona, snapshot=snapshot)
        except (InterpreterFailed, InterpreterTimeout) as error:
            failures += 1
            print(f"  FAILED: {type(error).__name__} {getattr(error, 'reason', '')} after {time.time() - started:.1f} s")
            continue
        print(summary(draft))
        print(f"  ({time.time() - started:.1f} s)")
        if arguments.json:
            print(json.dumps(draft, indent=2, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
