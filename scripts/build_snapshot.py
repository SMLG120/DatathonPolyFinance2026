#!/usr/bin/env python3
"""Build the data snapshot the Lambdas read, locally. No AWS access.

    python3 scripts/build_snapshot.py            # -> dist/snapshots/<snapshot_id>/...
    python3 scripts/build_snapshot.py --check    # validate and print the id, write nothing

Inputs (never committed where their terms forbid it, see docs/data-sources.md):

    data/processed/{instruments,holdings,market_data,controversies,sources}.json
    contracts/scenarios/{robert,mateo,amira}.json      (fictional portfolios, committed)

Output: one directory, ``dist/snapshots/<snapshot_id>/`` (``dist/`` is git-ignored), holding those
files, ``scenarios/<persona>.json`` and ``manifest.json``. The id is derived from the SHA-256 of
every file, so it changes whenever any number changes, and it is recorded with every
investigation. The directory layout is exactly the S3 layout: each file goes to
``s3://<data bucket>/snapshots/<snapshot_id>/<relative name>``.

Every file is validated with the contract validators before anything is written; a snapshot
that would make a check wrong (a portfolio position missing from the registry, a market-data
source id missing from the source registry) stops the build.

This script uploads nothing. The upload is a deploy step (scripts/deploy.md, "Data snapshot"):
the printed ``uploads`` list pairs each local file with its S3 key.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import byb_contracts  # noqa: E402

from backend.common.data import DATA_FILES, PERSONA_IDS, DataUnavailable, build_manifest, strict_json, validate_snapshot_documents  # noqa: E402

# Source-registry ids of the market data, so price and FX evidence is labelled FACT with its source.
DATA_SOURCES = {"prices": "starter_prices_daily", "fx_usdcad": "starter_fx_usdcad"}


class SnapshotError(Exception):
    pass


def _read(path: Path) -> tuple[bytes, object]:
    if "credential" in path.name.lower():
        raise SnapshotError(f"refusing to read {path.name}")
    try:
        raw = path.read_bytes()
        return raw, strict_json(raw)  # refuses NaN, Infinity and numbers that overflow
    except (OSError, ValueError) as error:
        raise SnapshotError(f"{path.relative_to(REPO_ROOT)} cannot be read as JSON ({type(error).__name__}). "
                            "The processed data files are git-ignored: build them with data/scripts/build_processed.py.") from error


def build(processed: Path, scenarios: Path) -> tuple[dict, dict[str, bytes]]:
    """(manifest, contents). Raises SnapshotError or byb_contracts.ContractError on invalid input."""
    contents: dict[str, bytes] = {}
    documents: dict[str, object] = {}
    for name in DATA_FILES:
        contents[f"{name}.json"], documents[name] = _read(processed / f"{name}.json")
    loaded = {persona_id: _read(scenarios / f"{persona_id}.json") for persona_id in PERSONA_IDS}
    try:
        # Exactly the checks the Lambdas repeat when they load the snapshot (backend/common/data.py).
        validate_snapshot_documents(documents, [scenario for _, scenario in loaded.values()], DATA_SOURCES)
    except DataUnavailable as error:
        raise SnapshotError(str(error)) from error
    registry = documents["instruments"]["instruments"]
    valuation_date = documents["market_data"]["valuation_date"]
    for persona_id in PERSONA_IDS:
        raw, scenario = loaded[persona_id]
        if scenario["persona"]["persona_id"] != persona_id:
            raise SnapshotError(f"scenarios/{persona_id}.json describes persona {scenario['persona']['persona_id']!r}")
        if scenario["portfolio"]["valuation_date"] != valuation_date:
            raise SnapshotError(f"{persona_id}: portfolio valuation date {scenario['portfolio']['valuation_date']} differs from the market data's {valuation_date}")
        missing = [p["instrument_id"] for p in scenario["portfolio"]["positions"] if p["instrument_id"] not in registry]
        if missing:
            raise SnapshotError(f"{persona_id}: positions not in the instrument registry: {missing}")
        contents[f"scenarios/{persona_id}.json"] = raw
    manifest = build_manifest(valuation_date, contents, DATA_SOURCES)
    contents["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    return manifest, contents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Before You Buy data snapshot (local, no AWS).")
    parser.add_argument("--processed-dir", default=str(REPO_ROOT / "data" / "processed"))
    parser.add_argument("--scenarios-dir", default=str(REPO_ROOT / "contracts" / "scenarios"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "dist" / "snapshots"))
    parser.add_argument("--check", action="store_true", help="validate and print the summary without writing")
    arguments = parser.parse_args(argv)
    try:
        manifest, contents = build(Path(arguments.processed_dir), Path(arguments.scenarios_dir))
    except (SnapshotError, byb_contracts.ContractError) as error:
        print(f"build_snapshot.py: {error}", file=sys.stderr)
        return 1
    snapshot_id = manifest["snapshot_id"]
    target = Path(arguments.output_dir) / snapshot_id
    if not arguments.check:
        for name, data in contents.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(json.dumps({
        "snapshot_id": snapshot_id,
        "valuation_date": manifest["valuation_date"],
        "written_to": None if arguments.check else str(target),
        "total_bytes": sum(len(data) for data in contents.values()),
        "stack_parameter": {"DataSnapshotId": snapshot_id},
        "uploads": [{"file": f"{target}/{name}", "s3_key": f"snapshots/{snapshot_id}/{name}", "bytes": len(data),
                     "content_type": "application/json; charset=utf-8"} for name, data in sorted(contents.items())],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
