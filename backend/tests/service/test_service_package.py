"""Packaging: same sources, same bytes; tests and caches stay out."""

import importlib.util
import io
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def packager():
    spec = importlib.util.spec_from_file_location("byb_package_script", REPO_ROOT / "scripts" / "package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SOURCES = [(name, name) for name in ["backend/api", "backend/worker", "backend/agents", "backend/common"]]


def test_pk01_build_is_deterministic(packager, tmp_path):
    first = packager.package(REPO_ROOT, SOURCES, tmp_path / "a")
    second = packager.package(REPO_ROOT, SOURCES, tmp_path / "b")
    assert first["sha256"] == second["sha256"]
    assert Path(first["path"]).read_bytes() == Path(second["path"]).read_bytes()
    assert Path(first["path"]).name == f"byb-backend-{first['sha256'][:16]}.zip"
    assert first["s3_key"] == f"lambda/byb-backend-{first['sha256'][:16]}.zip"


def test_pk02_archive_holds_the_handlers_and_no_tests_or_caches(packager, tmp_path):
    summary = packager.package(REPO_ROOT, SOURCES, tmp_path)
    with zipfile.ZipFile(io.BytesIO(Path(summary["path"]).read_bytes())) as archive:
        names = archive.namelist()
        infos = archive.infolist()
    for required in [
        "backend/__init__.py",
        "backend/api/handler.py",
        "backend/api/authorizer.py",
        "backend/worker/handler.py",
        "backend/agents/loop.py",
        "backend/common/jobs.py",
    ]:
        assert required in names
    assert names == sorted(names)
    assert not any("tests" in name or "__pycache__" in name or name.endswith(".pyc") for name in names)
    assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
    assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)


def test_pk03_files_that_look_like_secrets_stop_the_build(packager, tmp_path):
    source = tmp_path / "src" / "pkg"
    source.mkdir(parents=True)
    (source / "ok.py").write_text("x = 1\n")
    (source / "aws_credentials.json").write_text("{}")
    with pytest.raises(packager.PackagingError):
        packager.collect(tmp_path / "src", [("pkg", "pkg")])


def test_pk04_syntax_errors_stop_the_build(packager, tmp_path):
    source = tmp_path / "src" / "pkg"
    source.mkdir(parents=True)
    (source / "broken.py").write_text("def (:\n")
    with pytest.raises(packager.PackagingError):
        packager.collect(tmp_path / "src", [("pkg", "pkg")])


# --------------------------------------------------------------------------- phase 2: the deployable zip


def _default_archive(packager, tmp_path):
    summary = packager.package(REPO_ROOT, list(packager.DEFAULT_SOURCES), tmp_path / "zip")
    with zipfile.ZipFile(io.BytesIO(Path(summary["path"]).read_bytes())) as archive:
        return summary, archive.namelist()


def test_pk05_default_zip_ships_engine_and_contracts_and_no_data(packager, tmp_path):
    summary, names = _default_archive(packager, tmp_path)
    for required in ["backend/__init__.py", "backend/api/handler.py", "backend/worker/handler.py", "backend/api/authorizer.py",
                     "backend/engine/check.py", "backend/engine/boundary.py", "backend/common/data.py",
                     "byb_contracts/__init__.py", "byb_contracts/schemas/api.schema.json", "byb_contracts/schemas/check_result.schema.json"]:
        assert required in names, required
    assert (REPO_ROOT / "backend" / "__init__.py").is_file()  # a real package marker, not one synthesized by the packager
    # No data of any kind: holdings, prices, registries, scenarios, fixtures, evidence write-ups.
    for name in names:
        parts = set(Path(name).parts)
        assert not parts & {"data", "fixtures", "scenarios", "processed", "starter", "raw", "evidence", "tests"}, name
        assert Path(name).suffix in {".py", ".json"} and "credential" not in name.lower() and not Path(name).name.startswith(".env")
    json_files = [name for name in names if name.endswith(".json")]
    assert json_files and all(name.startswith("byb_contracts/schemas/") and name.endswith(".schema.json") for name in json_files)
    # Lambda limits: 50 MB zipped, 250 MB unzipped (LEAD_DECISIONS D1). The zip is a few hundred kilobytes.
    assert summary["bytes"] < 2 * 1024 * 1024 < packager.MAX_ZIP_BYTES and summary["unzipped_bytes"] < packager.MAX_UNZIPPED_BYTES


def test_pk06_data_and_fixtures_can_never_be_packaged(packager, tmp_path):
    for source in ["data/processed", "data/starter", "contracts/fixtures/engine", "contracts/scenarios"]:
        with pytest.raises(packager.PackagingError):
            packager.package(REPO_ROOT, [(source, "x")], tmp_path)


def test_pk07_the_zip_runs_by_itself_with_only_boto3(packager, tmp_path):
    """Unzip, leave the repository, and serve a POST /check through the Lambda handler from the unzipped files only.

    Proves the archive is self-sufficient: handlers, engine, contracts package and bundled schemas resolve with
    nothing but the standard library and boto3 on the path. The data comes from a snapshot directory (a filesystem
    source here, S3 in Lambda), never from the zip.
    """
    import json
    import subprocess
    import sys

    from service_fakes import NVDA_REQUEST, scenario, snapshot_contents

    summary, _ = _default_archive(packager, tmp_path)
    unzipped, snapshot_dir = tmp_path / "task", tmp_path / "snapshot"
    with zipfile.ZipFile(summary["path"]) as archive:
        archive.extractall(unzipped)
    for name, data in snapshot_contents("robert_synthetic_universe").items():
        (snapshot_dir / name).parent.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / name).write_bytes(data)
    cap = scenario("robert")["scenario_rules"][0]
    body = {"persona_id": "robert", "policy_id": None, "policy_version": None, "purchase_request": NVDA_REQUEST, "draft_rules": [cap]}
    program = f"""
import json, sys
assert not any("{REPO_ROOT}" == p or p.startswith("{REPO_ROOT}/") for p in sys.path), sys.path
import backend.api.handler as api, backend.worker.handler, backend.api.authorizer, byb_contracts, backend.engine
from backend.common.config import ApiConfig
from backend.common.data import FileSnapshotSource, SnapshotLoader
assert byb_contracts.schema_dir().as_posix().endswith("byb_contracts/schemas"), byb_contracts.schema_dir()
class Clock:
    def time(self): return 1794668400.0
app = api.Api(store=None, policies=None, snapshots=SnapshotLoader(FileSnapshotSource({str(snapshot_dir)!r})), lambda_client=None,
              config=ApiConfig(data_bucket="b", worker_function_name="w", snapshot_id="unused"), clock=Clock())
response = app.handle({{"routeKey": "POST /check", "body": {json.dumps(json.dumps(body))}, "requestContext": {{"requestId": "r"}}}}, None)
result = json.loads(response["body"])
byb_contracts.validate_check_result(result)
print(json.dumps({{"status": response["statusCode"], "headline": result["summary"]["headline"], "version": result["calculation_version"],
                  "modules": sorted(m.split(".")[0] for m in sys.modules if m.split(".")[0] in ("numpy", "pandas", "yaml", "requests", "jsonschema"))}}))
"""
    site_packages = [p for p in sys.path if "site-packages" in p]
    completed = subprocess.run([sys.executable, "-S", "-c", program], cwd=tmp_path, capture_output=True, text=True, timeout=120,
                               env={"PYTHONPATH": ":".join([str(unzipped), *site_packages]), "PATH": "/usr/bin:/bin"})
    assert completed.returncode == 0, completed.stderr[-2000:]
    from backend import engine

    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {"status": 200, "headline": "HAS_FAIL", "version": engine.CALCULATION_VERSION, "modules": []}
