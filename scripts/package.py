#!/usr/bin/env python3
"""Build the Lambda deployment zip, deterministically.

    python3 scripts/package.py                 # -> dist/byb-backend-<sha16>.zip
    python3 scripts/package.py --list          # also print the packaged file names
    python3 scripts/package.py --include some/dir=archive_prefix

The zip holds the service (``backend/api``, ``worker``, ``agents``, ``common``), the calculation
engine (``backend/engine``) and the shared contracts: ``contracts/python/byb_contracts`` at the
archive root as ``byb_contracts`` with ``contracts/schemas`` inside it as ``byb_contracts/schemas``
(the bundled location ``byb_contracts.schema`` looks in; ``BYB_SCHEMA_DIR`` points at it too).

It holds NO data: no holdings, prices, registries, scenarios or fixtures. Data reaches the
functions as a snapshot in the private data bucket (``scripts/build_snapshot.py``). Any path
under ``data/`` or ``fixtures/`` stops the build.

The same sources always produce the same bytes (sorted entries, fixed
timestamps and permissions, no compression), so the SHA-256 in the file name
identifies the code. CloudFormation only redeploys a function when the S3 key
changes, which makes a content-addressed key the simplest correct trigger.

Only ``.py`` and ``.json`` files are packaged. Tests, caches and anything that
looks like a secret are left out; a file whose name looks like a credential
or ``.env`` file stops the build without being opened.

Standard library only. No AWS access: uploading is a separate step (see
``scripts/deploy.md``).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SOURCES = [
    ("backend/api", "backend/api"),
    ("backend/worker", "backend/worker"),
    ("backend/agents", "backend/agents"),
    ("backend/common", "backend/common"),
    ("backend/engine", "backend/engine"),
    ("contracts/python/byb_contracts", "byb_contracts"),
    ("contracts/schemas", "byb_contracts/schemas"),
]
# Never packaged, wherever they are asked for: redistribution-restricted data and synthetic fixtures.
FORBIDDEN_SOURCE_PARTS = {"data", "fixtures", "scenarios", "raw", "processed", "starter"}
# Lambda limits (LEAD_DECISIONS D1): 50 MB zipped for a direct upload, 250 MB unzipped.
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_UNZIPPED_BYTES = 250 * 1024 * 1024

INCLUDED_SUFFIXES = {".py", ".json"}
EXCLUDED_DIRECTORIES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "tests", "test", "node_modules", "evidence"}
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o100644


class PackagingError(Exception):
    pass


def _looks_sensitive(name: str) -> bool:
    lowered = name.lower()
    return "credential" in lowered or lowered.startswith(".env") or lowered.endswith((".pem", ".key"))


def collect(root: Path, sources: list[tuple[str, str]]) -> dict[str, bytes]:
    """Map archive name -> content for every packaged file."""
    files: dict[str, bytes] = {}
    for source, archive_prefix in sources:
        if FORBIDDEN_SOURCE_PARTS & set(Path(source).parts):
            raise PackagingError(f"refusing to package data or fixtures: {source}")
        base = root / source
        if not base.is_dir():
            raise PackagingError(f"source directory not found: {source}")
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(base)
            if any(part in EXCLUDED_DIRECTORIES for part in relative.parts[:-1]) or not path.is_file():
                continue
            if _looks_sensitive(path.name):
                raise PackagingError(f"refusing to package a file that looks like a secret: {source}/{relative}")
            if path.suffix not in INCLUDED_SUFFIXES or path.name.startswith("test_") or path.name == "conftest.py":
                continue
            archive_name = (Path(archive_prefix) / relative).as_posix()
            if archive_name in files:
                raise PackagingError(f"two sources map to the same archive path: {archive_name}")
            content = path.read_bytes()
            if path.suffix == ".py":
                try:
                    compile(content, archive_name, "exec")
                except SyntaxError as error:
                    raise PackagingError(f"syntax error in {archive_name}: {error}") from error
            files[archive_name] = content

    # Lambda imports "backend.api.handler". An explicit package marker makes
    # that resolution independent of anything else on the runtime's path.
    marker = root / "backend" / "__init__.py"
    if any(name.startswith("backend/") for name in files) and "backend/__init__.py" not in files:
        files["backend/__init__.py"] = marker.read_bytes() if marker.is_file() else b""
    if not files:
        raise PackagingError("nothing to package")
    return files


def build_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3  # Unix, so the permission bits below mean the same everywhere
            info.external_attr = FILE_MODE << 16
            archive.writestr(info, files[name])
    return buffer.getvalue()


def package(root: Path, sources: list[tuple[str, str]], output_directory: Path) -> dict[str, object]:
    files = collect(root, sources)
    data = build_zip(files)
    unzipped = sum(len(content) for content in files.values())
    if len(data) > MAX_ZIP_BYTES or unzipped > MAX_UNZIPPED_BYTES:
        raise PackagingError(f"the archive is too large for Lambda: {len(data)} bytes zipped, {unzipped} bytes unzipped")
    digest = hashlib.sha256(data).hexdigest()
    name = f"byb-backend-{digest[:16]}.zip"
    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / name
    path.write_bytes(data)
    return {
        "path": str(path),
        "s3_key": f"lambda/{name}",
        "sha256": digest,
        "bytes": len(data),
        "unzipped_bytes": unzipped,
        "files": sorted(files),
    }


def _parse_include(value: str) -> tuple[str, str]:
    source, _, prefix = value.partition("=")
    source = source.strip().strip("/")
    return source, (prefix.strip().strip("/") or source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic Lambda zip for Before You Buy.")
    parser.add_argument("--with-engine", action="store_true", help="accepted for compatibility; the engine is always packaged")
    parser.add_argument("--include", action="append", default=[], metavar="SRC[=ARCHIVE_PREFIX]", help="extra source directory, relative to the repository root")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "dist"), help="where to write the zip (default: dist/)")
    parser.add_argument("--list", action="store_true", help="print the packaged file names")
    arguments = parser.parse_args(argv)

    sources = list(DEFAULT_SOURCES)
    sources.extend(_parse_include(value) for value in arguments.include)

    try:
        summary = package(REPO_ROOT, sources, Path(arguments.output_dir))
    except PackagingError as error:
        print(f"package.py: {error}", file=sys.stderr)
        return 1
    files = summary.pop("files")
    summary["file_count"] = len(files)  # type: ignore[arg-type]
    if arguments.list:
        summary["files"] = files
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
