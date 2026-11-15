"""Write (or check) every generated contract file: engine fixtures, scenarios and API fixtures.

    python3 contracts/python/tools/build_fixtures.py          # rewrite the JSON files
    python3 contracts/python/tools/build_fixtures.py --check  # fail if a file on disk differs

The specs in this folder hold hand-entered values; this script only expands
boilerplate and computes policy content hashes. Standard library only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_lib import CONTRACTS, render_json  # noqa: E402


def planned_files() -> dict:
    import engine_cases
    import engine_universes

    files = {}
    engine = CONTRACTS / "fixtures" / "engine"
    for universe in (engine_universes.generic_universe(), engine_universes.robert_universe(), engine_universes.mateo_universe()):
        files[engine / f"{universe['universe_id']}.json"] = universe
    for case in engine_cases.all_cases():
        files[engine / f"{case['fixture_id']}.json"] = case
    try:
        import scenario_defs
    except ModuleNotFoundError:
        scenario_defs = None
    if scenario_defs is not None:
        for name, scenario in scenario_defs.all_scenarios().items():
            files[CONTRACTS / "scenarios" / f"{name}.json"] = scenario
    try:
        import api_fixtures
    except ModuleNotFoundError:
        api_fixtures = None
    if api_fixtures is not None:
        for fixture in api_fixtures.all_fixtures():
            files[CONTRACTS / "fixtures" / "api" / f"{fixture['fixture_id']}.json"] = fixture
    return files


def main(argv: list) -> int:
    check = "--check" in argv
    stale = []
    files = planned_files()
    for path, value in files.items():
        text = render_json(value)
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(CONTRACTS)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if check:
        if stale:
            print("STALE (re-run build_fixtures.py):", *stale, sep="\n  ")
            return 1
        print(f"{len(files)} generated files are up to date")
        return 0
    print(f"wrote {len(files)} files under {CONTRACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
