"""Reference data of one data snapshot: sector labels and company names, indexed once (standard library only).

The interpreter never lets the model name a company or a sector freely. Every id and label it may use comes from
here, and every match is computed by the server from the investor's own characters. A match is a *hint* for the
model and a *gate* for the draft, never a reading of meaning.

Frozen interface (WP2 and WP4 code against it; change it only together with them)
--------------------------------------------------------------------------------
``_Reference(snapshot)``
    ``snapshot`` has ``registry: dict[str, dict]`` and ``holdings: dict`` (``funds -> {fund: {holdings: [row]}}``).
    Funds themselves are skipped; only issuers held directly or through a fund are indexed.

Attributes (read-only after construction):

* ``ids: list[str]`` - every issuer id of the snapshot, sorted. The tool schema's company enum is built from it.
* ``sectors: list[str]`` - sector labels the data reports, sorted, at most ``MAX_SECTOR_LABELS``.
* ``display: dict[str, str]`` - issuer id -> display name (first name seen, at most 80 characters).
* ``sector_of: dict[str, str]`` - issuer id -> its sector label, when the data gives one.

Methods (all deterministic, no model involved):

* ``companies_in(text: str) -> list[str]`` - sorted issuer ids whose cleaned name, id or alias is written in
  ``text`` as whole words, whose unique first word is written capitalised and is not a common word, or whose ticker
  stands alone (any case when at least 3 characters and not a common word, upper case otherwise); at most
  ``MAX_COMPANY_CANDIDATES``.
* ``find(words: str) -> list[str]`` - for the ``find_companies`` lookup: ``companies_in(words)`` when it finds
  anything, else close spellings and name prefixes; at most ``MAX_LOOKUP_MATCHES``.
* ``describe(issuer_id: str) -> {"issuer_id", "name", "sector"}`` - what a lookup returns about one company.
* ``sector_members(sector: str, limit: int = 8) -> list[str]`` - example names labelled ``sector``.

``_normalize(text) -> str`` lower-cases and collapses everything but ``[a-z0-9]`` to single spaces; names, ids and
the investor's words are all compared in this form.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from backend.agents.themes import COMPANY_ALIASES

MAX_COMPANY_CANDIDATES = 40
MAX_SECTOR_LABELS = 120
MAX_LOOKUP_MATCHES = 5

# Legal-form words and parentheses that do not identify a company ("Exxon Mobil Corp" is "exxon mobil").
_NAME_NOISE_RE = re.compile(r"\([^)]*\)|\b(inc|corp|corporation|co|company|ltd|limited|plc|sa|nv|ag|class [a-c]|cl [a-c]|com|the)\b")
# Ordinary words that also start a company id ("royal" for ROYAL_BANK_OF_CANADA) or spell a ticker ("all", "key").
# Such a word alone is not read as a company: "I want royal treatment" names none. The full name or an alias still
# matches ("Royal Bank of Canada", "RBC"). A closed list; a miss only adds a hint, which grounding still checks.
COMMON_WORDS = frozenset("""
    all american any are best big can central city first general global good great home key low main national new now
    one out pacific power public real royal safe sun target true union united well west western world
""".split())
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_TICKER_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9.-]{1,11}(?![A-Za-z0-9])")


def _normalize(text: str) -> str:
    """The comparison form of names and words: lower case, only letters and digits, single spaces."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


class _Reference:
    """Sector labels and company names of one snapshot, indexed once."""

    def __init__(self, snapshot: Any) -> None:
        sectors: set[str] = set()
        names: dict[str, set[str]] = {}
        tickers: dict[str, set[str]] = {}
        display: dict[str, str] = {}
        sector_of: dict[str, str] = {}

        def add(issuer_id: Any, name: Any, instrument_id: Any, sector: Any) -> None:
            if not isinstance(issuer_id, str) or not issuer_id:
                return
            phrases = names.setdefault(issuer_id, set())
            phrases.add(_normalize(issuer_id))
            if isinstance(name, str) and name:
                display.setdefault(issuer_id, name[:80])
                cleaned = _normalize(_NAME_NOISE_RE.sub(" ", name.lower()))
                if len(cleaned) >= 4:
                    phrases.add(cleaned)
            if isinstance(instrument_id, str) and instrument_id:
                tickers.setdefault(issuer_id, set()).update({instrument_id, instrument_id.split(".")[0]})
            if isinstance(sector, str) and sector:
                sector_of.setdefault(issuer_id, sector)

        for instrument in snapshot.registry.values():
            if instrument.get("is_fund"):
                continue
            equity_sector = instrument.get("sector") if instrument.get("equity_scope") else None
            add(instrument.get("issuer_id"), instrument.get("name"), instrument.get("instrument_id"), equity_sector)
            if isinstance(equity_sector, str) and equity_sector:
                sectors.add(equity_sector)
        for fund in (snapshot.holdings.get("funds") or {}).values():
            for row in fund.get("holdings") or []:
                add(row.get("issuer_id"), row.get("name"), row.get("instrument_id"), row.get("sector"))
                if isinstance(row.get("sector"), str) and row["sector"]:
                    sectors.add(row["sector"])

        # Common names ("Google" for Alphabet): an alias resolves only to a company whose cleaned name is in the data.
        by_name: dict[str, set[str]] = {}
        for issuer_id, phrases in names.items():
            for phrase in phrases:
                by_name.setdefault(phrase, set()).add(issuer_id)
        for alias, target in COMPANY_ALIASES.items():
            for issuer_id in by_name.get(target, ()):
                names[issuer_id].add(_normalize(alias))

        self.ids = sorted(names)
        self.sectors = sorted(sectors)[:MAX_SECTOR_LABELS]
        self.display = display
        self.sector_of = sector_of
        self._phrases: dict[str, set[str]] = {}
        first_words: dict[str, set[str]] = {}
        for issuer_id, phrases in names.items():
            for phrase in phrases:
                if len(phrase) >= 3:
                    self._phrases.setdefault(phrase, set()).add(issuer_id)
            first = _normalize(issuer_id).split(" ")[0] if _normalize(issuer_id) else ""
            if len(first) >= 5:
                first_words.setdefault(first, set()).add(issuer_id)
        # The first word of a company id ("exxon" for EXXON_MOBIL) counts only when a single company starts with it.
        # It is kept apart from the full phrases because it is weaker evidence: companies_in requires it capitalised.
        self._first_words = {first: issuers for first, issuers in first_words.items()
                             if len(issuers) == 1 and first not in COMMON_WORDS and first not in self._phrases}
        self._tickers: dict[str, set[str]] = {}
        for issuer_id, symbols in tickers.items():
            for symbol in symbols:
                if len(symbol) >= 2:
                    self._tickers.setdefault(symbol.upper(), set()).add(issuer_id)

    def companies_in(self, text: str) -> list[str]:
        """Issuer ids whose name, id or ticker is written in ``text`` (deterministic; no model involved).

        Full names, ids and aliases match in any case. The weaker signals are guarded against ordinary words: a
        unique first word must be written capitalised ("Johnson", not "royal treatment"), and a ticker written in
        lower case ("msft") must have at least 3 characters and not be a common word ("all")."""
        words = _normalize(text).split(" ")
        found: set[str] = set()
        for size in range(1, 7):
            for start in range(0, len(words) - size + 1):
                found.update(self._phrases.get(" ".join(words[start:start + size]), ()))
        for word in _WORD_RE.findall(text):
            if word[0].isupper():
                found.update(self._first_words.get(word.lower(), ()))
        for symbol in _TICKER_RE.findall(text):
            for candidate in {symbol, symbol.rstrip(".-")}:
                if candidate.isupper() or (len(candidate) >= 3 and candidate.lower() not in COMMON_WORDS):
                    found.update(self._tickers.get(candidate.upper(), ()))
        return sorted(found)[:MAX_COMPANY_CANDIDATES]

    def find(self, words: str) -> list[str]:
        """Issuer ids for words the investor wrote, for the agent's lookup tool: exact matches first, then close spellings
        ("Microsft") and name prefixes ("Royal"). Deterministic: the server matches, the model only chose the words."""
        exact = self.companies_in(words)
        if exact:
            return exact[:MAX_LOOKUP_MATCHES]
        wanted = _normalize(words)
        if len(wanted) < 3:
            return []
        found: list[str] = []
        close = difflib.get_close_matches(wanted, list(self._phrases), n=MAX_LOOKUP_MATCHES, cutoff=0.82)
        prefixed = [phrase for phrase in sorted(self._phrases) if len(wanted) >= 4 and phrase.startswith(wanted + " ")]
        for phrase in close + prefixed:
            for issuer_id in sorted(self._phrases[phrase]):
                if issuer_id not in found:
                    found.append(issuer_id)
        return found[:MAX_LOOKUP_MATCHES]

    def describe(self, issuer_id: str) -> dict[str, Any]:
        return {"issuer_id": issuer_id, "name": self.display.get(issuer_id, issuer_id), "sector": self.sector_of.get(issuer_id)}

    def sector_members(self, sector: str, limit: int = 8) -> list[str]:
        """Names of companies the data labels with ``sector`` (examples for the agent, not a definition)."""
        return sorted(self.display.get(i, i) for i, label in self.sector_of.items() if label == sector)[:limit]
