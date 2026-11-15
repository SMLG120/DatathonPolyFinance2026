"""Shared helpers for the data-evidence scripts (standard library only).

Every script in this directory starts with

    sys.path.insert(0, str(Path(__file__).resolve().parent))

so that it also works under ``python3 -I`` (isolated mode), which is how the
scripts that read downloaded, untrusted files are meant to be run. This
directory holds only our own code; downloads live under ``data/raw/``.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
STARTER_DIR = DATA_DIR / "starter"
RAW_DIR = DATA_DIR / "raw"
MANIFEST_DIR = DATA_DIR / "manifests"
PROCESSED_DIR = DATA_DIR / "processed"

SCHEMA_VERSION = "1.0.0"
# Lead decision D2: valuation date = last starter-data date.
VALUATION_DATE = "2026-11-12"

RAW_MANIFEST = MANIFEST_DIR / "raw_files_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def rel(path: Path) -> str:
    """Repo-relative POSIX path, used in manifests and reports."""
    return Path(path).resolve().relative_to(REPO_ROOT).as_posix()


def write_bytes_atomic(path: Path, payload: bytes, *, overwrite: bool) -> None:
    """Write through a temp file + rename so a crash never leaves partial output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite {path}")
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o644)  # mkstemp creates 0600; these are ordinary project files
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def dump_json(obj, *, compact: bool = False) -> bytes:
    if compact:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def load_json(path: Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
