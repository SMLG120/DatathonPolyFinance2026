"""Data snapshot: everything a verdict depends on apart from the policy and the request.

A snapshot is one immutable directory, identified by ``snapshot_id``::

    manifest.json            id, valuation date, per-file SHA-256, market-data source ids
    instruments.json         instrument registry            (instrument.schema.json#/$defs/registry)
    holdings.json            fund holdings snapshot         (holdings_snapshot.schema.json)
    market_data.json         adjusted prices and USD/CAD    (market_data.schema.json)
    controversies.json       controversy registry
    sources.json             source registry
    scenarios/<persona>.json fictional persona scenario with its portfolio (scenario.schema.json)

Issuer-derived holdings and Yahoo-derived prices are not redistributable through Git, so the
snapshot is never part of the code zip. ``scripts/build_snapshot.py`` builds it locally from
``data/processed`` and ``contracts/scenarios``; in AWS it lives in the private data bucket under
``snapshots/<snapshot_id>/`` and the id is configuration (``DATA_SNAPSHOT_ID``).

The id is derived from the content hashes, so two different data sets can never share an id, and
the id recorded with a job says exactly which numbers produced its result.

Two sources implement the same small interface: the filesystem (tests, local runs) and S3 (Lambda).
A loaded snapshot is cached in memory for the life of the container.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Protocol

DATA_FILES = ("instruments", "holdings", "market_data", "controversies", "sources")
PERSONA_IDS = ("robert", "mateo", "amira")
MANIFEST_SCHEMA_VERSION = 1
SNAPSHOT_ID_RE = re.compile(r"snap-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9a-f]{12}")


class DataUnavailable(Exception):
    """The snapshot (or one of its files) cannot be read or does not match its manifest."""


class SnapshotSource(Protocol):
    def read(self, name: str) -> bytes:
        """Bytes of ``<name>`` (a path relative to the snapshot root). Raises DataUnavailable."""


class FileSnapshotSource:
    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def read(self, name: str) -> bytes:
        try:
            return (self._directory / name).read_bytes()
        except OSError as error:
            raise DataUnavailable(f"snapshot file {name} cannot be read ({type(error).__name__})") from error


class S3SnapshotSource:
    """Reads ``snapshots/<snapshot_id>/<name>`` from the private data bucket (``s3:GetObject`` only)."""

    def __init__(self, s3: Any, bucket: str, snapshot_id: str) -> None:
        if SNAPSHOT_ID_RE.fullmatch(snapshot_id) is None:
            raise DataUnavailable("the configured snapshot id is malformed")
        self._s3, self._bucket, self._prefix = s3, bucket, f"snapshots/{snapshot_id}/"

    def read(self, name: str) -> bytes:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=self._prefix + name)
            body = response["Body"]
            try:
                return body.read()
            finally:
                body.close()
        except Exception as error:  # noqa: BLE001 - any storage failure means the same thing to the caller
            raise DataUnavailable(f"snapshot file {name} cannot be read ({type(error).__name__})") from error


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_id_for(valuation_date: str, file_hashes: dict[str, str]) -> str:
    """Content-derived id: the valuation date plus 12 hex characters over every file hash."""
    digest = hashlib.sha256()
    for name in sorted(file_hashes):
        digest.update(name.encode("utf-8") + b"\x00" + file_hashes[name].encode("ascii") + b"\x00")
    return f"snap-{valuation_date}-{digest.hexdigest()[:12]}"


class Snapshot:
    def __init__(self, snapshot_id: str, manifest: dict, files: dict[str, Any], scenarios: dict[str, dict]) -> None:
        self.snapshot_id = snapshot_id
        self.manifest = manifest
        self.instruments = files["instruments"]
        self.holdings = files["holdings"]
        self.market_data = files["market_data"]
        self.controversies = files["controversies"]
        self.sources = files["sources"]
        self.scenarios = scenarios
        # Source ids of the market data, so price and FX evidence is labelled FACT by the engine.
        self.data_sources: dict[str, str] = dict(manifest.get("data_sources") or {})

    def scenario(self, persona_id: str) -> dict | None:
        return self.scenarios.get(persona_id)

    @property
    def registry(self) -> dict[str, dict]:
        return self.instruments["instruments"]

    def purchasable_instrument_ids(self) -> list[str]:
        """In the registry AND with a price series (contracts/api.md section 2)."""
        prices = self.market_data.get("prices", {})
        return sorted(instrument_id for instrument_id in self.registry if instrument_id in prices)


class SnapshotLoader:
    """Loads, verifies and caches one snapshot."""

    def __init__(self, source: SnapshotSource, expected_snapshot_id: str | None = None) -> None:
        self._source = source
        self._expected = expected_snapshot_id
        self._snapshot: Snapshot | None = None

    def _json(self, name: str, expected_sha256: str | None) -> Any:
        raw = self._source.read(name)
        if expected_sha256 is not None and sha256_hex(raw) != expected_sha256:
            raise DataUnavailable(f"snapshot file {name} does not match the manifest")
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise DataUnavailable(f"snapshot file {name} is not valid JSON") from error

    def load(self) -> Snapshot:
        if self._snapshot is not None:
            return self._snapshot
        manifest = self._json("manifest.json", None)
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
            raise DataUnavailable("the snapshot manifest is malformed")
        snapshot_id = manifest.get("snapshot_id")
        hashes = {name: (entry or {}).get("sha256") for name, entry in manifest["files"].items()}
        if not isinstance(snapshot_id, str) or snapshot_id != snapshot_id_for(str(manifest.get("valuation_date")), hashes):
            raise DataUnavailable("the snapshot id does not match the snapshot content")
        if self._expected is not None and snapshot_id != self._expected:
            raise DataUnavailable("the snapshot found is not the configured one")
        files = {}
        for name in DATA_FILES:
            key = f"{name}.json"
            if key not in hashes:
                raise DataUnavailable(f"the snapshot manifest does not list {key}")
            files[name] = self._json(key, hashes[key])
        scenarios = {}
        for key in sorted(hashes):
            if key.startswith("scenarios/") and key.endswith(".json"):
                scenario = self._json(key, hashes[key])
                scenarios[scenario["persona"]["persona_id"]] = scenario
        self._snapshot = Snapshot(snapshot_id, manifest, files, scenarios)
        return self._snapshot


def build_manifest(valuation_date: str, contents: dict[str, bytes], data_sources: dict[str, str]) -> dict:
    """Manifest for ``contents`` (relative name -> bytes). Used by the build script and the tests."""
    files = {name: {"sha256": sha256_hex(data), "bytes": len(data)} for name, data in sorted(contents.items())}
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "snapshot_id": snapshot_id_for(valuation_date, {name: entry["sha256"] for name, entry in files.items()}),
        "valuation_date": valuation_date,
        "data_sources": dict(data_sources),
        "files": files,
    }
