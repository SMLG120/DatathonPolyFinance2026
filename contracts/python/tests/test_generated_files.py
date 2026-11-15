"""The JSON files under contracts/fixtures and contracts/scenarios are exactly what the generator writes.

A hand edit of a generated file, or a spec change that was not regenerated, fails here:

    python3 contracts/python/tools/build_fixtures.py
"""

from __future__ import annotations

import subprocess
import sys

import build_fixtures
from paths import API, CONTRACTS, ENGINE, SCENARIO_DIR


def test_check_mode_reports_every_generated_file_as_up_to_date():
    script = CONTRACTS / "python" / "tools" / "build_fixtures.py"
    done = subprocess.run([sys.executable, "-B", str(script), "--check"], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "generated files are up to date" in done.stdout


def test_no_json_file_is_left_over_from_an_earlier_generation():
    planned = set(build_fixtures.planned_files())
    on_disk = {path for folder in (ENGINE, API, SCENARIO_DIR) for path in folder.glob("*.json")}
    assert on_disk == planned, f"not generated: {sorted(p.name for p in on_disk - planned)}; missing: {sorted(p.name for p in planned - on_disk)}"


def test_check_mode_detects_a_stale_file(tmp_path, monkeypatch):
    """--check must fail when a file differs: run it against a copy in which one file was edited."""
    files = build_fixtures.planned_files()
    target = next(path for path in files if path.name == "M2.json")
    edited = tmp_path / "M2.json"
    edited.write_text(target.read_text(encoding="utf-8").replace('"UNKNOWN"', '"PASS"', 1), encoding="utf-8")
    monkeypatch.setattr(build_fixtures, "planned_files", lambda: {edited: files[target]})
    monkeypatch.setattr(build_fixtures, "CONTRACTS", tmp_path)
    assert build_fixtures.main(["--check"]) == 1
    edited.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    assert build_fixtures.main(["--check"]) == 0
