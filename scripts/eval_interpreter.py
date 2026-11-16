"""Evaluate the rule interpreter ("Add a limit in your own words") on a corpus of sentences, with the REAL model.

The corpus is ``scripts/interpreter_corpus.json``. Every item is a sentence with expectations that are scored
deterministically against the interpretation document the interpreter returns. The interpreter is built exactly as
``scripts/try_interpreter.py`` builds it (``backend.api.handler._build_interpreter`` on the synthetic Mateo snapshot,
same timeouts, retries and 20 s budget). Nothing is stored.

From the repository root:

    uv run --no-project --with boto3 python scripts/eval_interpreter.py
    uv run --no-project --with boto3 python scripts/eval_interpreter.py --category oil_fossil --concurrency 2
    uv run --no-project --with boto3 python scripts/eval_interpreter.py --ids cap-001,reg-001 --report /tmp/x.json
    uv run --no-project --with boto3 python scripts/eval_interpreter.py --rescore /tmp/interpreter_eval.json --report /tmp/re.json

Scoring (see ``score``) separates two things:

* **safety** - a guarantee was broken: contract-invalid output, a rule that is not PROPOSED, a threshold whose quote
  is not a literal percentage of the investor's text (an invented number), a rule that contradicts the polarity of
  the text (``unsafe`` patterns of the item), an echoed span that is not verbatim, or a sentence shown to the investor
  that is not a server template (model prose leak). Always enforced.
* **correctness** - the expected reading was produced (``require``/``ask``/``flag``/``any_of``) and nothing the item
  forbids appears (``forbid``/``forbid_together``/``no_number``/``max_rules``/``max_clarifications``/``nonempty``).

An item passes when it is correct and has no safety violation. A model failure (502/504) is an ``error``.

Expectation format (``expect`` of a corpus item; every key is optional):

    require            [pattern]   each must be matched
    forbid             [pattern]   none may be matched (correctness)
    unsafe             [pattern]   none may be matched (SAFETY: the rule contradicts the text)
    forbid_together    [[pattern]] not every pattern of a group may be matched at once (correctness)
    ask                [ask]       each must be matched by a distinct clarification
    flag               [flag]      each must be matched by an unsupported entry
    any_of             [block]     at least one block (same keys, no nested any_of) must hold
    no_number          bool        every threshold, in rules and in options, is null
    max_rules          int         at most this many proposed_rules
    max_clarifications int         at most this many clarifications
    nonempty           bool        at least one objective, rule, clarification or unsupported entry

    pattern = {"rule_type": str, "params": {..subset..}, "threshold": number | null | "any", "via": "rule" | "option" | "either"}
        params is a deep subset match; a list in params matches when its items are a subset of the actual list.
        threshold defaults to "any". via defaults to "rule" for require/forbid/forbid_together, "either" for unsafe.
        "option" = the proposed_rule of a SUPPORTED clarification option.
    ask  = {"about": str (case-insensitive substring of about_words), "options_all": [option_id], "options_any": [option_id]}
    flag = {"code": str | [str], "words": str (case-insensitive substring of words)}
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import statistics
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for extra in (REPO_ROOT / "contracts" / "python", REPO_ROOT, REPO_ROOT / "backend" / "tests" / "service", REPO_ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

CORPUS_PATH = REPO_ROOT / "scripts" / "interpreter_corpus.json"
DEFAULT_REPORT = Path("/tmp/interpreter_eval.json")

EXPECT_KEYS = {"require", "forbid", "unsafe", "forbid_together", "ask", "flag", "any_of", "no_number", "max_rules",
               "max_clarifications", "nonempty"}
PATTERN_KEYS = {"rule_type", "params", "threshold", "via"}
ASK_KEYS = {"about", "options_all", "options_any"}
FLAG_KEYS = {"code", "words"}
ITEM_KEYS = {"id", "category", "text", "expect", "tags", "note"}
VIAS = ("rule", "option", "either")
RULE_TYPES = ("max_issuer_exposure", "min_issuer_exposure", "exclusion", "controversy_exclusion", "scenario_loss_budget")
UNSUPPORTED_CODES = ("UNSUPPORTED_DEFINITION", "UNSUPPORTED_RULE_TYPE", "OUT_OF_SCOPE", "INSTRUCTION_IGNORED")


# --------------------------------------------------------------------------- corpus validation


def expectation_errors(expect: Any, where: str = "expect", nested: bool = False) -> list[str]:
    """Problems with one ``expect`` block (empty when it is well formed)."""
    errors: list[str] = []
    if not isinstance(expect, dict):
        return [f"{where}: must be an object"]
    for key in expect:
        if key not in EXPECT_KEYS or (nested and key == "any_of"):
            errors.append(f"{where}: unknown key {key!r}")

    def pattern_errors(pattern: Any, at: str) -> None:
        if not isinstance(pattern, dict):
            errors.append(f"{at}: pattern must be an object")
            return
        errors.extend(f"{at}: unknown key {k!r}" for k in pattern if k not in PATTERN_KEYS)
        if "rule_type" in pattern and pattern["rule_type"] not in RULE_TYPES:
            errors.append(f"{at}: unknown rule_type {pattern['rule_type']!r}")
        if "params" in pattern and not isinstance(pattern["params"], dict):
            errors.append(f"{at}: params must be an object")
        threshold = pattern.get("threshold", "any")
        if not (threshold is None or threshold == "any" or (isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and 0 <= threshold <= 1)):
            errors.append(f"{at}: threshold must be a fraction in [0, 1], null or 'any'")
        if pattern.get("via", "rule") not in VIAS:
            errors.append(f"{at}: via must be one of {VIAS}")

    for key in ("require", "forbid", "unsafe"):
        value = expect.get(key, [])
        if not isinstance(value, list):
            errors.append(f"{where}.{key}: must be a list")
            continue
        for i, pattern in enumerate(value):
            pattern_errors(pattern, f"{where}.{key}[{i}]")
    groups = expect.get("forbid_together", [])
    if not isinstance(groups, list):
        errors.append(f"{where}.forbid_together: must be a list")
    else:
        for i, group in enumerate(groups):
            if not isinstance(group, list) or len(group) < 2:
                errors.append(f"{where}.forbid_together[{i}]: must be a list of at least two patterns")
                continue
            for j, pattern in enumerate(group):
                pattern_errors(pattern, f"{where}.forbid_together[{i}][{j}]")
    for i, ask in enumerate(expect.get("ask", []) if isinstance(expect.get("ask", []), list) else [None]):
        if not isinstance(ask, dict):
            errors.append(f"{where}.ask[{i}]: must be an object")
            continue
        errors.extend(f"{where}.ask[{i}]: unknown key {k!r}" for k in ask if k not in ASK_KEYS)
        for k in ("options_all", "options_any"):
            if k in ask and not (isinstance(ask[k], list) and ask[k] and all(isinstance(o, str) for o in ask[k])):
                errors.append(f"{where}.ask[{i}].{k}: must be a non-empty list of option ids")
    for i, flag in enumerate(expect.get("flag", []) if isinstance(expect.get("flag", []), list) else [None]):
        if not isinstance(flag, dict):
            errors.append(f"{where}.flag[{i}]: must be an object")
            continue
        errors.extend(f"{where}.flag[{i}]: unknown key {k!r}" for k in flag if k not in FLAG_KEYS)
        codes = flag.get("code")
        codes = [] if codes is None else ([codes] if isinstance(codes, str) else codes)
        if any(c not in UNSUPPORTED_CODES for c in codes):
            errors.append(f"{where}.flag[{i}]: unknown unsupported code in {codes!r}")
    for key in ("no_number", "nonempty"):
        if key in expect and not isinstance(expect[key], bool):
            errors.append(f"{where}.{key}: must be a boolean")
    for key in ("max_rules", "max_clarifications"):
        if key in expect and not (isinstance(expect[key], int) and not isinstance(expect[key], bool) and expect[key] >= 0):
            errors.append(f"{where}.{key}: must be a non-negative integer")
    if "any_of" in expect and not nested:
        blocks = expect["any_of"]
        if not isinstance(blocks, list) or len(blocks) < 2:
            errors.append(f"{where}.any_of: must be a list of at least two blocks")
        else:
            for i, block in enumerate(blocks):
                errors.extend(expectation_errors(block, f"{where}.any_of[{i}]", nested=True))
    return errors


def corpus_errors(corpus: Any) -> list[str]:
    """Problems with the whole corpus file (empty when it is well formed)."""
    if not isinstance(corpus, dict) or not isinstance(corpus.get("items"), list) or not isinstance(corpus.get("categories"), dict):
        return ["corpus: must be an object with 'categories' (object) and 'items' (list)"]
    errors = []
    seen: set[str] = set()
    used: dict[str, int] = {}
    for i, item in enumerate(corpus["items"]):
        where = f"items[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: must be an object")
            continue
        errors.extend(f"{where}: unknown key {k!r}" for k in item if k not in ITEM_KEYS)
        for key in ("id", "category", "text"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f"{where}: {key} must be a non-empty string")
        if item.get("id") in seen:
            errors.append(f"{where}: duplicate id {item.get('id')!r}")
        seen.add(item.get("id"))
        if item.get("category") not in corpus["categories"]:
            errors.append(f"{where}: unknown category {item.get('category')!r}")
        used[item.get("category")] = used.get(item.get("category"), 0) + 1
        if "tags" in item and not (isinstance(item["tags"], list) and all(isinstance(t, str) for t in item["tags"])):
            errors.append(f"{where}: tags must be a list of strings")
        errors.extend(f"{where}.{e}" for e in expectation_errors(item.get("expect")))
    errors.extend(f"categories: {name!r} has no item" for name in corpus["categories"] if not used.get(name))
    return errors


def load_corpus(path: Path = CORPUS_PATH) -> dict[str, Any]:
    corpus = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = corpus_errors(corpus)
    if errors:
        raise ValueError("invalid corpus:\n  " + "\n  ".join(errors[:30]))
    return corpus


# --------------------------------------------------------------------------- literal numbers (safety)

_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
          "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19,
          # French
          "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sept": 7, "huit": 8, "neuf": 9,
          "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
         "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}
_PERCENT_WORD = r"(?:%|percent\b|per\s*cent\b|pct\b|pc\b|pour\s*cent\b|pourcent\b|por\s*ciento\b|prozent\b)"
_DIGIT_PERCENT_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d+)?)\s*" + _PERCENT_WORD, re.IGNORECASE)
_WORD_NUMBER = "|".join(sorted(list(_UNITS) + list(_TENS) + ["hundred", "cent"], key=len, reverse=True))
_WORD_PERCENT_RE = re.compile(rf"\b((?:(?:{_WORD_NUMBER})[\s-]*(?:and\s+|et\s+)?)+)" + _PERCENT_WORD, re.IGNORECASE)
_FRACTIONS = {"half": 0.5, "moitie": 0.5, "moitié": 0.5, "third": 1 / 3, "tiers": 1 / 3, "quarter": 0.25, "quart": 0.25,
              "fifth": 0.2, "cinquieme": 0.2, "cinquième": 0.2, "tenth": 0.1, "dixieme": 0.1, "dixième": 0.1}
_FRACTION_RE = re.compile(r"\b(" + "|".join(_FRACTIONS) + r")\b", re.IGNORECASE)
_RATIO_RE = re.compile(r"(?<![\d/])(\d{1,3})\s*/\s*(\d{1,3})(?![\d/])")


def _words_value(words: str) -> float | None:
    total, seen = 0, False
    for token in re.findall(r"[a-zà-ÿ]+", words.lower()):
        if token in ("and", "et"):
            continue
        if token in _UNITS:
            total += _UNITS[token]
        elif token in _TENS:
            total += _TENS[token]
        elif token in ("hundred", "cent"):
            total = (total or 1) * 100
        else:
            return None
        seen = True
    return float(total) if seen else None


def literal_values(quote: str) -> list[float]:
    """Fractions a quote literally denotes: digit percentages, spelled-out percentages and fraction words.
    A bare decimal ("0.10") or a bare number ("10") denotes nothing: its unit is not written. Full-width characters
    ("10％") are read as their plain forms, as the investor sees them."""
    quote = unicodedata.normalize("NFKC", quote)
    values = [float(m.group(1).replace(",", ".")) / 100 for m in _DIGIT_PERCENT_RE.finditer(quote)]
    for match in _WORD_PERCENT_RE.finditer(quote):
        value = _words_value(match.group(1))
        if value is not None:
            values.append(value / 100)
    values.extend(_FRACTIONS[m.group(1).lower()] for m in _FRACTION_RE.finditer(quote))
    values.extend(int(m.group(1)) / int(m.group(2)) for m in _RATIO_RE.finditer(quote) if 0 < int(m.group(2)) and int(m.group(1)) <= int(m.group(2)))
    return values


# --------------------------------------------------------------------------- server-written text (safety)

_LITERALS: list[str] | None = None
_TEMPLATE_SOURCES = ("backend/agents/*.py", "contracts/python/byb_contracts/*.py")


def server_literals() -> list[str]:
    """Every string constant (and constant part of an f-string or a .format template) in the server's agent and
    contract modules, longest first. A sentence shown to the investor must be made of these plus echoed data."""
    global _LITERALS
    if _LITERALS is None:
        found: set[str] = set()
        for pattern in _TEMPLATE_SOURCES:
            for path in sorted(REPO_ROOT.glob(pattern)):
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"))
                except (OSError, SyntaxError):
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        for piece in re.split(r"\{[^{}]*\}", node.value):
                            if len(piece.strip()) >= 3:
                                found.add(piece)
        _LITERALS = sorted(found, key=len, reverse=True)
    return _LITERALS


def unexplained_words(shown: str, text: str, data_words: list[str]) -> list[str]:
    """Words of ``shown`` that are neither a server template, the investor's own words, nor snapshot data."""
    rest = shown
    # Template pieces and snapshot data together, longest first. Either order alone is wrong: a short template piece
    # ("dia", "any", "_CA_") would cut a company name or id apart ("Canadian National Railway", "SYN_CA_ISSUER_1"),
    # and a short data word ("Energy") would cut a template that quotes it ("... 'avoid Energy' ..."). A template
    # piece can start with the apostrophe that closes an echoed span ("'{sector}': ...").
    for piece in sorted({*server_literals(), *data_words}, key=len, reverse=True):
        if piece and piece in rest:
            rest = rest.replace(piece, " ")
    # Quoted echoes of the investor's text ('...').
    rest = re.sub(r"'([^']*)'", lambda m: " " if m.group(1) in text else m.group(0), rest)
    rest = re.sub(r"\d{4}-\d{2}-\d{2}", " ", rest)
    return [w for w in re.findall(r"[A-Za-zÀ-ÿ]{3,}", rest) if w not in text]


# --------------------------------------------------------------------------- matching


def _subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and all(any(_subset(e, a) for a in actual) for e in expected)
    return expected == actual


def _threshold_ok(expected: Any, actual: Any) -> bool:
    if expected == "any":
        return True
    if expected is None:
        return actual is None
    return isinstance(actual, (int, float)) and math.isclose(float(actual), float(expected), abs_tol=1e-6)


def candidate_rules(interpretation: dict, via: str) -> list[dict]:
    rules: list[dict] = []
    if via in ("rule", "either"):
        rules.extend(interpretation.get("proposed_rules") or [])
    if via in ("option", "either"):
        for clarification in interpretation.get("clarifications") or []:
            for option in clarification.get("options") or []:
                if option.get("supported") and option.get("proposed_rule"):
                    rules.append(option["proposed_rule"])
    return rules


def pattern_matches(pattern: dict, interpretation: dict, default_via: str = "rule") -> bool:
    for rule in candidate_rules(interpretation, pattern.get("via", default_via)):
        if "rule_type" in pattern and rule.get("rule_type") != pattern["rule_type"]:
            continue
        if "params" in pattern and not _subset(pattern["params"], rule.get("parameters")):
            continue
        if not _threshold_ok(pattern.get("threshold", "any"), rule.get("threshold")):
            continue
        return True
    return False


def _describe(pattern: dict) -> str:
    bits = [pattern.get("rule_type", "any rule")]
    if "params" in pattern:
        bits.append(json.dumps(pattern["params"], separators=(",", ":")))
    if pattern.get("threshold", "any") != "any":
        bits.append(f"threshold={pattern['threshold']}")
    if "via" in pattern:
        bits.append(f"via={pattern['via']}")
    return " ".join(bits)


def _ask_matches(ask: dict, clarification: dict) -> bool:
    if "about" in ask and ask["about"].lower() not in (clarification.get("about_words") or "").lower():
        return False
    ids = {o.get("option_id") for o in clarification.get("options") or []}
    if "options_all" in ask and not set(ask["options_all"]) <= ids:
        return False
    if "options_any" in ask and not set(ask["options_any"]) & ids:
        return False
    return True


def _flag_matches(flag: dict, item: dict) -> bool:
    codes = flag.get("code")
    if codes is not None and item.get("code") not in ([codes] if isinstance(codes, str) else codes):
        return False
    return "words" not in flag or flag["words"].lower() in (item.get("words") or "").lower()


def _assign(wanted: list[dict], available: list[dict], matches: Any) -> bool:
    """Each wanted entry matched by a distinct available entry (small bipartite matching)."""
    def place(i: int, used: set[int]) -> bool:
        if i == len(wanted):
            return True
        return any(j not in used and matches(wanted[i], available[j]) and place(i + 1, used | {j}) for j in range(len(available)))
    return place(0, set())


def block_failures(block: dict, interpretation: dict) -> list[str]:
    """Correctness failures of one expectation block (empty when it holds)."""
    failures = []
    for pattern in block.get("require", []):
        if not pattern_matches(pattern, interpretation, "rule"):
            failures.append(f"missing {_describe(pattern)}")
    for pattern in block.get("forbid", []):
        if pattern_matches(pattern, interpretation, "rule"):
            failures.append(f"forbidden {_describe(pattern)}")
    for group in block.get("forbid_together", []):
        if all(pattern_matches(p, interpretation, "rule") for p in group):
            failures.append("forbidden together: " + " + ".join(_describe(p) for p in group))
    clarifications = interpretation.get("clarifications") or []
    asks = block.get("ask", [])
    if asks and not _assign(asks, clarifications, _ask_matches):
        failures.append("missing question " + json.dumps(asks, separators=(",", ":")))
    flags = block.get("flag", [])
    unsupported = interpretation.get("unsupported") or []
    if flags and not _assign(flags, unsupported, _flag_matches):
        failures.append("missing unsupported entry " + json.dumps(flags, separators=(",", ":")))
    if block.get("no_number") and any(r.get("threshold") is not None for r in candidate_rules(interpretation, "either")):
        failures.append("a number was taken where none should be")
    if "max_rules" in block and len(interpretation.get("proposed_rules") or []) > block["max_rules"]:
        failures.append(f"{len(interpretation.get('proposed_rules') or [])} proposed rules, at most {block['max_rules']} expected")
    if "max_clarifications" in block and len(clarifications) > block["max_clarifications"]:
        failures.append(f"{len(clarifications)} questions, at most {block['max_clarifications']} expected")
    if block.get("nonempty") and not any(interpretation.get(k) for k in ("objectives", "proposed_rules", "clarifications", "unsupported")):
        failures.append("empty draft")
    return failures


def safety_violations(item: dict, interpretation: dict, data_words: list[str] | None = None) -> list[str]:
    """Broken guarantees. Independent of how the expected reading is phrased."""
    violations = []
    text = item["text"]
    try:
        from byb_contracts import interpretation_errors
        contract = interpretation_errors(interpretation)
    except Exception as error:  # noqa: BLE001 - a crash on the document is itself a contract failure
        contract = [f"validator crashed: {type(error).__name__}"]
    violations.extend(f"contract: {e}" for e in contract[:3])
    if interpretation.get("original_words") != text:
        violations.append("echo: original_words is not the request text")
    all_rules = [("proposed_rules", r) for r in interpretation.get("proposed_rules") or []]
    for c in interpretation.get("clarifications") or []:
        all_rules.extend((f"option {o.get('option_id')}", o["proposed_rule"]) for o in c.get("options") or [] if o.get("proposed_rule"))
    for where, rule in all_rules:
        if rule.get("status") != "PROPOSED":
            violations.append(f"status: {where} has status {rule.get('status')}")
        if rule.get("original_words") is not None and rule["original_words"] not in text:
            violations.append(f"echo: {where} original_words is not a verbatim span")
        threshold = rule.get("threshold")
        if threshold is not None:
            quote = rule.get("threshold_quote") or ""
            if rule.get("threshold_source") != "USER_WORDS" or not quote or quote not in text:
                violations.append(f"invented number: {where} threshold {threshold} has no verbatim quote")
            elif not any(math.isclose(v, float(threshold), abs_tol=1e-6) for v in literal_values(quote)):
                violations.append(f"invented number: {where} threshold {threshold} is not what {quote!r} literally says")
    for o in interpretation.get("objectives") or []:
        if o.get("original_words") is not None and o["original_words"] not in text:
            violations.append("echo: objective original_words is not a verbatim span")
    for pattern in item.get("expect", {}).get("unsafe", []):
        if pattern_matches(pattern, interpretation, "either"):
            violations.append(f"polarity: contradicts the text: {_describe(pattern)}")
    shown = []
    for c in interpretation.get("clarifications") or []:
        shown.append(c.get("question") or "")
        for o in c.get("options") or []:
            shown.extend([o.get("label") or "", o.get("description") or ""])
    shown.extend(u.get("reason") or "" for u in interpretation.get("unsupported") or [])
    shown.extend(r.get("scope_description") or "" for _, r in all_rules)
    leaked = []
    for sentence in shown:
        leaked.extend(unexplained_words(sentence, text, data_words or []))
    if leaked:
        violations.append("prose leak: words not from a server template: " + " ".join(sorted(set(leaked))[:8]))
    return violations


def score(item: dict, interpretation: dict | None, error: str | None = None, data_words: list[str] | None = None) -> dict[str, Any]:
    """Score one item. ``error`` is a model failure (no interpretation)."""
    if interpretation is None:
        return {"passed": False, "correct": False, "error": error or "no interpretation", "safety": [], "failures": [error or "no interpretation"]}
    expect = item.get("expect", {})
    safety = safety_violations(item, interpretation, data_words)
    failures = block_failures(expect, interpretation)
    blocks = expect.get("any_of") or []
    if blocks:
        alternatives = [block_failures(b, interpretation) for b in blocks]
        if all(alternatives):
            failures.append("no acceptable reading: " + " | ".join("; ".join(a) for a in alternatives))
    correct = not failures
    return {"passed": correct and not safety, "correct": correct, "error": None, "safety": safety, "failures": failures}


# --------------------------------------------------------------------------- running against the real model


def _data_words(snapshot: Any) -> list[str]:
    words: set[str] = set()
    for instrument in snapshot.registry.values():
        for key in ("issuer_id", "name", "sector", "instrument_id"):
            if isinstance(instrument.get(key), str):
                words.add(instrument[key])
    for fund in (snapshot.holdings.get("funds") or {}).values():
        for row in fund.get("holdings") or []:
            for key in ("issuer_id", "name", "sector", "instrument_id"):
                if isinstance(row.get(key), str):
                    words.add(row[key])
    return sorted(words)


def run(items: list[dict], *, universe: str, model: str, persona: str, concurrency: int) -> list[dict]:
    import boto3
    from botocore.config import Config

    from backend.agents.interpreter import InterpreterFailed, InterpreterTimeout
    from backend.api.handler import _build_interpreter
    from backend.common import log
    from backend.common.clock import SystemClock
    from backend.common.config import ApiConfig
    from try_interpreter import load_snapshot, summary

    log.configure("ERROR", sys.stderr)
    snapshot = load_snapshot(universe)
    data_words = _data_words(snapshot)
    config = ApiConfig(data_bucket="unused", worker_function_name="unused", model_id=model, interpreter_enabled=True)
    interpreter = _build_interpreter(boto3.session.Session(region_name="us-east-1"), Config, config, SystemClock())
    calls = threading.local()
    converse = interpreter._model.converse

    def counted(**kwargs):  # every model call's token usage, for the item being run on this thread
        response, record = converse(**kwargs)
        calls.usage.append(record.get("usage") or {})
        return response, record

    interpreter._model.converse = counted

    def one(item: dict) -> dict:
        calls.usage = []
        started = time.time()
        interpretation, error = None, None
        try:
            interpretation = interpreter.interpret(text=item["text"], persona_id=persona, snapshot=snapshot)
        except (InterpreterFailed, InterpreterTimeout) as failure:
            error = f"{type(failure).__name__} {getattr(failure, 'reason', '')}".strip()
        except Exception as failure:  # noqa: BLE001 - a crash is reported, not hidden
            error = f"crash {type(failure).__name__}: {failure}"
        seconds = round(time.time() - started, 2)
        result = score(item, interpretation, error, data_words)
        result.update({"id": item["id"], "category": item["category"], "text": item["text"], "seconds": seconds,
                       "tags": item.get("tags", []), "usage": list(calls.usage),
                       "summary": summary(interpretation) if interpretation is not None else None,
                       "interpretation": interpretation})
        mark = "PASS" if result["passed"] else ("ERR " if result["error"] else ("UNSAFE" if result["safety"] else "FAIL"))
        print(f"  {mark:6} {item['id']:<12} {seconds:5.1f}s  {item['text'][:70]}", file=sys.stderr, flush=True)
        return result

    with ThreadPoolExecutor(max_workers=max(1, min(4, concurrency))) as pool:
        return list(pool.map(one, items))


def rescore(items: list[dict], previous: Path, universe: str) -> list[dict]:
    """Score the interpretations of an earlier report against the current corpus and scorer, without the model."""
    from try_interpreter import load_snapshot

    data_words = _data_words(load_snapshot(universe))
    stored = {r["id"]: r for r in json.loads(previous.read_text(encoding="utf-8"))["results"]}
    results = []
    for item in items:
        old = stored.get(item["id"])
        if old is None or old.get("text") != item["text"]:
            continue  # new or changed sentence: it needs a model run
        result = score(item, old.get("interpretation"), old.get("error"), data_words)
        result.update({k: old.get(k) for k in ("seconds", "summary", "interpretation")})
        result.update({"id": item["id"], "category": item["category"], "text": item["text"], "tags": item.get("tags", [])})
        results.append(result)
    return results


def report(results: list[dict], categories: dict[str, str]) -> dict[str, Any]:
    per_category: dict[str, dict[str, int]] = {}
    for r in results:
        c = per_category.setdefault(r["category"], {"total": 0, "passed": 0, "correct": 0, "unsafe": 0, "errors": 0})
        c["total"] += 1
        c["passed"] += r["passed"]
        c["correct"] += r["correct"]
        c["unsafe"] += bool(r["safety"])
        c["errors"] += bool(r["error"])
    latencies = sorted(r["seconds"] for r in results if r.get("seconds") is not None)
    # Per model call: "input" is what Bedrock bills as fresh input; "prompt" adds the tokens read from or written to
    # the prompt cache, i.e. the whole prompt the model saw.
    usages = [u for r in results for u in r.get("usage") or []]
    fresh = sorted(u.get("input_tokens") or 0 for u in usages)
    prompt = sorted((u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_write_input_tokens") or 0)
                    for u in usages)
    p95 = latencies[min(len(latencies) - 1, math.ceil(0.95 * len(latencies)) - 1)] if latencies else None
    return {
        "total": len(results),
        "passed": sum(r["passed"] for r in results),
        "correct": sum(r["correct"] for r in results),
        "failed": sum(not r["passed"] and not r["error"] for r in results),
        "errors": sum(bool(r["error"]) for r in results),
        "items_with_safety_violations": sum(bool(r["safety"]) for r in results),
        "safety_violations": sum(len(r["safety"]) for r in results),
        "latency_median_seconds": round(statistics.median(latencies), 2) if latencies else None,
        "latency_p95_seconds": p95,
        "model_calls": len(usages),
        "input_tokens_median_per_call": statistics.median(fresh) if fresh else None,
        "prompt_tokens_median_per_call": statistics.median(prompt) if prompt else None,
        "cache_read_calls": sum(1 for u in usages if u.get("cache_read_input_tokens")),
        "output_tokens_median_per_call": statistics.median(sorted(u.get("output_tokens") or 0 for u in usages)) if usages else None,
        "per_category": {name: per_category[name] for name in categories if name in per_category},
    }


def _reason(result: dict) -> str:
    if result["error"]:
        return f"ERROR {result['error']}"
    if result["safety"]:
        return "UNSAFE " + result["safety"][0]
    return result["failures"][0] if result["failures"] else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", default=str(CORPUS_PATH))
    parser.add_argument("--ids", help="comma-separated item ids")
    parser.add_argument("--category", help="comma-separated categories")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--concurrency", type=int, default=3, help="worker threads, at most 4")
    parser.add_argument("--universe", default="mateo_synthetic_universe")
    parser.add_argument("--model", default="us.anthropic.claude-sonnet-5-5")
    parser.add_argument("--persona", default="mateo", choices=("robert", "mateo", "amira"))
    parser.add_argument("--rescore", metavar="REPORT", help="score the interpretations stored in an earlier report again (no model call)")
    arguments = parser.parse_args()

    corpus = load_corpus(Path(arguments.corpus))
    items = corpus["items"]
    if arguments.ids:
        wanted = set(arguments.ids.split(","))
        items = [i for i in items if i["id"] in wanted]
    if arguments.category:
        wanted = set(arguments.category.split(","))
        items = [i for i in items if i["category"] in wanted]
    if arguments.limit:
        items = items[: arguments.limit]
    if not items:
        print("no corpus item selected", file=sys.stderr)
        return 2

    started = time.time()
    if arguments.rescore:
        results = rescore(items, Path(arguments.rescore), arguments.universe)
    else:
        results = run(items, universe=arguments.universe, model=arguments.model, persona=arguments.persona, concurrency=arguments.concurrency)
    totals = report(results, corpus["categories"])
    totals["wall_seconds"] = round(time.time() - started, 1)
    Path(arguments.report).write_text(json.dumps({"model": arguments.model, "universe": arguments.universe, "totals": totals, "results": results},
                                                 indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'category':<22} {'pass':>9} {'correct':>8} {'unsafe':>7} {'errors':>7}")
    for name, c in totals["per_category"].items():
        print(f"{name:<22} {c['passed']:>4}/{c['total']:<4} {c['correct']:>8} {c['unsafe']:>7} {c['errors']:>7}")
    print(f"\npassed {totals['passed']}/{totals['total']}  correct {totals['correct']}  failed {totals['failed']}  errors {totals['errors']}  "
          f"items with safety violations {totals['items_with_safety_violations']} ({totals['safety_violations']} violations)")
    print(f"latency median {totals['latency_median_seconds']} s  p95 {totals['latency_p95_seconds']} s  wall {totals['wall_seconds']} s")
    print(f"model calls {totals['model_calls']}  median input tokens/call {totals['input_tokens_median_per_call']} (fresh)  "
          f"{totals['prompt_tokens_median_per_call']} (whole prompt)  cache reads on {totals['cache_read_calls']} calls")
    failing = [r for r in results if not r["passed"]]
    if failing:
        print("\nfailing:")
        for r in failing:
            print(f"  {r['id']:<12} {_reason(r)[:160]}")
    print(f"\nreport: {arguments.report}")
    return 0 if not any(r["safety"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
