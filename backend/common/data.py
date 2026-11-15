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

Nothing is served from a snapshot that has not been checked. ``SnapshotLoader.load`` verifies, in
this order: the manifest and the content-derived id, the SHA-256 of every file, strict JSON (no
``NaN``, no ``Infinity``, no number that overflows to infinity), every data file against its
contract validator, every scenario against the scenario contract, and the consistency the
look-through arithmetic relies on (a fund's declared coverage equals the sum of its rows, every
row and instrument names its issuer; ``backend.engine.guard``). Any failure is ``DataUnavailable``:
the API answers 500 and an investigation ends ``FAILED / DATA_UNAVAILABLE``; no result is produced.
``scripts/build_snapshot.py`` runs the same checks before a snapshot is written.
"""

from __future__ import annotations

import hashlib
import json
import re
import math
from pathlib import Path
from typing import Any, Iterable, Protocol

import byb_contracts

from backend.engine.guard import data_problems

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


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"{name} is not a JSON number")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):  # "1e999" is valid JSON text and parses to infinity
        raise ValueError("a number is too large to be represented")
    return value


def strict_json(raw: bytes) -> Any:
    """Parse UTF-8 JSON, refusing NaN, Infinity and numbers that overflow. Raises ValueError."""
    return json.loads(raw.decode("utf-8"), parse_constant=_refuse_constant, parse_float=_finite_float)


def _first(error: byb_contracts.ContractError) -> str:
    return f"{error.what}: {error.errors[0] if error.errors else 'invalid'}"[:300]


def validate_snapshot_documents(files: dict[str, Any], scenarios: Iterable[dict], data_sources: dict[str, str]) -> None:
    """Contract and consistency checks of a whole snapshot. Raises DataUnavailable naming the first problem.

    Shared by the loader (every cold start) and ``scripts/build_snapshot.py`` (before writing).
    """
    try:
        byb_contracts.validate_instrument_registry(files["instruments"])
        byb_contracts.validate_holdings_snapshot(files["holdings"])
        byb_contracts.validate_market_data(files["market_data"])
        byb_contracts.validate_source_registry(files["sources"])
        byb_contracts.validate_controversy_registry(files["controversies"], known_source_ids=files["sources"]["sources"].keys())
        for scenario in scenarios:
            byb_contracts.validate_scenario(scenario)
    except byb_contracts.ContractError as error:
        raise DataUnavailable(f"the snapshot does not satisfy the data contract ({_first(error)})") from error
    problems = data_problems(files["instruments"], files["holdings"], files["market_data"], files["controversies"])
    if problems:
        raise DataUnavailable("the snapshot data is not consistent (" + "; ".join(problems) + ")")
    for role, source_id in sorted(data_sources.items()):
        if source_id not in files["sources"]["sources"]:
            raise DataUnavailable(f"the market-data source id for {role} is not in the source registry")


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
        self._subject_ids: frozenset[str] | None = None

    def scenario(self, persona_id: str) -> dict | None:
        return self.scenarios.get(persona_id)

    @property
    def registry(self) -> dict[str, dict]:
        return self.instruments["instruments"]

    def subject_ids(self) -> frozenset[str]:
        """Every instrument, fund and issuer id of the snapshot (used to recognise a name in model-written text)."""
        if self._subject_ids is None:
            ids = set(self.registry) | {instrument["issuer_id"] for instrument in self.registry.values()}
            for fund in self.holdings.get("funds", {}).values():
                ids.update(row["issuer_id"] for row in fund["holdings"])
            self._subject_ids = frozenset(ids)
        return self._subject_ids

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
            return strict_json(raw)
        except (ValueError, UnicodeDecodeError, RecursionError) as error:
            raise DataUnavailable(f"snapshot file {name} is not strict JSON") from error

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
        loaded = [self._json(key, hashes[key]) for key in sorted(hashes) if key.startswith("scenarios/") and key.endswith(".json")]
        data_sources = manifest.get("data_sources") or {}
        if not isinstance(data_sources, dict) or not all(isinstance(v, str) for v in data_sources.values()):
            raise DataUnavailable("the snapshot manifest is malformed")
        validate_snapshot_documents(files, loaded, data_sources)
        scenarios = {scenario["persona"]["persona_id"]: scenario for scenario in loaded}
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
