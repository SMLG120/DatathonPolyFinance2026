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
