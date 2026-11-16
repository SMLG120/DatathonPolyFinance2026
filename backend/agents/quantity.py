"""Deterministic reading of the amounts, dates and sentences in the investor's own characters (standard library only).

The model never supplies a number. It only points at the characters that hold one (a ``quantity_mention``, a
``date_mention``, a ``non_quantity`` mention); this module reads those characters and nothing else. Every function is
pure and closed-world: a form it does not recognise gives a non-numeric outcome (a question upstream), never a guess.

* ``parse(mention)``: one amount as written ("10%", "2,5 %", "ten percent", "a quarter", "1/10", "0.10", "5-10%")
  becomes a ``Quantity``. Only PERCENT and PERCENT_WORDS are thresholds the compiler may draft directly; FRACTION is
  offered pre-filled for confirmation; every other form carries no value.
* ``hedged_near``: an approximation word on or right next to the mention ("about 10%", "10% or so").
* ``number_tokens``, ``is_year``, ``horizon_confirmed``, ``name_part_confirmed``, ``followed_by_percent``: the
  lexical checks behind number ownership (every digit in a clause must belong to something the server understood).
* ``parse_date(mention)``: "since 2020" / "depuis mars 2021" -> an ISO start date.
* ``sentence_spans(text)``: the abbreviation-aware splitter behind the same-sentence check.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

# --------------------------------------------------------------------------- forms

PERCENT = "PERCENT"
PERCENT_WORDS = "PERCENT_WORDS"
FRACTION = "FRACTION"
UNIT_UNCLEAR = "UNIT_UNCLEAR"
RANGE = "RANGE"
MALFORMED = "MALFORMED"
HEDGED = "HEDGED"
FORMS = (PERCENT, PERCENT_WORDS, FRACTION, UNIT_UNCLEAR, RANGE, MALFORMED, HEDGED)
# The only forms whose value may become a USER_STATED threshold without a confirmation step.
THRESHOLD_FORMS = (PERCENT, PERCENT_WORDS)

MAX_DECIMALS = 4


@dataclass(frozen=True)
class Quantity:
    """One amount read from the investor's characters.

    ``value`` is a portfolio fraction (10% -> 0.1) for PERCENT, PERCENT_WORDS and FRACTION, and None for every other
    form. ``quote`` is the mention trimmed of surrounding blanks and punctuation, so it is still a verbatim slice of
    the investor's text and ``parse(quote)`` gives the same result. ``reason`` is a short code for the log explaining
    a non-threshold form (None for PERCENT).
    """

    form: str
    value: float | None
    quote: str
    reason: str | None


# --------------------------------------------------------------------------- vocabulary

# Written after the number. "pc" and the words only count after a digit or a blank, so "10pc" and "ten pc" read but a
# word that merely ends in "pc" does not.
_PERCENT_MARK = r"(?:\s*%|(?:(?<=\d)|\s+)(?:percent|per\s+cent|pct|pc|pour\s+cent|pourcent|por\s+ciento|prozent))"
_MARK_SUFFIX_RE = re.compile(r"^(?P<body>.*?)" + _PERCENT_MARK + r"$")
_DIGITS_RE = re.compile(r"(?P<int>\d+)(?:[.,](?P<frac>\d+))?")
_NUMBER_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*")
_RATIO_RE = re.compile(r"(?P<n>\d+)\s*[/⁄]\s*(?P<m>\d+)")

# An exact bound written after the amount is part of the direction, not an approximation: "10% or less" is precise.
_BOUND_SUFFIX_RE = re.compile(r"\s+(?:or\s+(?:less|more|lower|higher|under|below|fewer)|ou\s+(?:moins|plus)|o\s+(?:menos|m[aá]s)|"
                              r"oder\s+(?:weniger|mehr))$")

# Words that make an amount approximate. Searched on the mention and on the few words before it.
_HEDGE_RE = re.compile(
    r"[~≈]|\bca\.|\b(?:around|about|roughly|approx|approximately|circa|maybe|perhaps|probably|possibly|nearly|almost|"
    r"close\s+to|something\s+like|give\s+or\s+take|more\s+or\s+less|or\s+so|ish|"
    r"environ|[aà]\s+peu\s+pr[eè]s|plus\s+ou\s+moins|peut[\s-][eê]tre|autour\s+de|presque|quasiment|"
    r"aproximadamente|alrededor\s+de|m[aá]s\s+o\s+menos|unos|unas|cerca\s+de|casi|quiz[aá]s?|tal\s+vez|"
    r"etwa|ungef[aä]hr|zirka|rund|vielleicht)\b")
# Approximations that only ever trail an amount ("10% per company, give or take", "10 % environ"). Words that lead an
# amount ("roughly", "~") are left out: after the mention they would belong to the next amount, not this one.
_TRAILING_HEDGE_RE = re.compile(r"\b(?:or\s+so|give\s+or\s+take|ish|more\s+or\s+less|plus\s+ou\s+moins|environ|m[aá]s\s+o\s+menos|o\s+as[ií])\b")
_HEDGE_WINDOW_TOKENS = 3

# Two amounts joined like this are a range or an alternative ("5-10%", "between 5% and 10%", "5 or 6%").
_RANGE_JOIN_RE = re.compile(r"\s*[-‐-―]\s*|\s+(?:to|and|or|et|[aà]|au|ou|y|o|u|hasta|und|oder|bis)\s+")
_RANGE_LEAD_RE = re.compile(r"^(?:between|from|entre|de|desde|zwischen|von)\s+")

_CURRENCY_RE = re.compile(r"[$€£¥]|\b(?:usd|eur|cad|dollars?|euros?)\b")
_EXPONENT_RE = re.compile(r"\d\s*e\s*[+\-−]?\d")
_SIGN_RE = re.compile(r"^[+\-−–—±]|[+\-−±]$")
_LETTER_IN_DIGITS_RE = re.compile(r"\d[^\W\d_]|[^\W\d_]\d")
_TRIM = " \t\r\n.,;:!?\"'()[]{}«»“”‘’"

# Time units that mark a number as a horizon ("over the next 5 years", "dans 3 ans"). Compared lower-case.
TIME_UNITS = frozenset((
    "year", "years", "yr", "yrs", "month", "months", "week", "weeks", "day", "days", "decade", "decades",
    "an", "ans", "année", "années", "annee", "annees", "mois", "semaine", "semaines", "jour", "jours", "décennie", "décennies",
    "año", "años", "ano", "anos", "mes", "meses", "semana", "semanas", "día", "días", "dia", "dias", "década", "décadas",
    "jahr", "jahre", "jahren", "jahres", "monat", "monate", "monaten", "woche", "wochen", "tag", "tage", "tagen", "jahrzehnt", "jahrzehnte",
))
_HORIZON_DISTANCE = 2
_WORD_TOKEN_RE = re.compile(r"[^\W_]+|[~≈]")

_YEAR_RE = re.compile(r"(?:19|20)\d\d")


def _accentless(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word) if not unicodedata.combining(c)).replace("ß", "ss")


def _with_variants(table: dict[str, Fraction | int]) -> dict[str, Fraction | int]:
    """Each written form plus its unaccented spelling ("dieciseis", "dreissig"), as investors often type them."""
    out = dict(table)
    for word, value in table.items():
        out.setdefault(_accentless(word), value)
    return out


def _compose(units: dict[int, str], tens: dict[int, str], join) -> dict[str, int]:
    """The units, the tens, and every ten + unit not already a unit, spelled by ``join(ten, ten_word, unit)``."""
    out = {word: n for n, word in units.items()} | {word: n for n, word in tens.items()}
    for ten, ten_word in tens.items():
        for unit in range(1, 10):
            if ten + unit not in units:
                for word in join(ten, ten_word, unit):
                    out[word] = ten + unit
    return out


def _english() -> dict[str, int]:
    units = dict(enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                           "sixteen seventeen eighteen nineteen".split()))
    tens = dict(zip(range(20, 100, 10), "twenty thirty forty fifty sixty seventy eighty ninety".split()))
    table = _compose(units, tens, lambda ten, word, unit: [f"{word} {units[unit]}"])
    return table | {"hundred": 100, "a hundred": 100, "one hundred": 100}


def _french() -> dict[str, int]:
    units = dict(enumerate("zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize".split()))
    units |= {17: "dix sept", 18: "dix huit", 19: "dix neuf"}
    tens = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}

    def join(ten, word, unit):
        return [f"{word} et un"] if unit == 1 else [f"{word} {units[unit]}"]

    table = _compose(units, tens, join) | {"une": 1, "cent": 100, "quatre vingt": 80, "quatre vingts": 80}
    # 70-79 and 81-99 count on from 60 and 80 ("soixante douze", "quatre vingt dix neuf").
    for base, word, first in ((60, "soixante", 10), (80, "quatre vingt", 1)):
        for extra in range(first, 20):
            table[f"{word} {units[extra]}"] = base + extra
    table["soixante et onze"] = 71
    # Belgian and Swiss tens count like the others.
    regional = {70: "septante", 80: "huitante", 90: "nonante"}
    table |= _compose(units, regional, join) | {"octante": 80}
    return table


def _spanish() -> dict[str, int]:
    units = dict(enumerate("cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis "
                           "diecisiete dieciocho diecinueve veinte veintiuno veintidós veintitrés veinticuatro veinticinco veintiséis "
                           "veintisiete veintiocho veintinueve".split()))
    tens = dict(zip(range(30, 100, 10), "treinta cuarenta cincuenta sesenta setenta ochenta noventa".split()))
    table = _compose(units, tens, lambda ten, word, unit: [f"{word} y {units[unit]}"] + ([f"{word} y un", f"{word} y una"] if unit == 1 else []))
    return table | {"un": 1, "una": 1, "veintiún": 21, "veintiuna": 21, "cien": 100, "ciento": 100}


def _german() -> dict[str, int]:
    units = dict(enumerate("null eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf dreizehn vierzehn fünfzehn "
                           "sechzehn siebzehn achtzehn neunzehn".split()))
    tens = dict(zip(range(20, 100, 10), "zwanzig dreißig vierzig fünfzig sechzig siebzig achtzig neunzig".split()))
    table = _compose(units, tens, lambda ten, word, unit: [f"{'ein' if unit == 1 else units[unit]}und{word}"])
    return table | {"ein": 1, "eine": 1, "hundert": 100, "einhundert": 100}


def _number_words() -> dict[str, int]:
    """Closed EN/FR/ES/DE table of the written numbers 0-100, keyed by the lower-case, hyphen-free spelling.

    Languages are merged into one table: a spelling shared by two languages ("un", "six") means the same number in
    both, which the tests assert.
    """
    table: dict[str, int] = {}
    for language in (_english(), _french(), _spanish(), _german()):
        table |= language
    return _with_variants(table)


NUMBER_WORDS: dict[str, int] = _number_words()

# Spelled fractions of the whole portfolio. "half" etc. are amounts the investor wrote, but they are offered for
# confirmation (FRACTION) rather than drafted, since "half" is often loose speech.
FRACTION_WORDS: dict[str, Fraction] = _with_variants({
    **{f"{article}{word}": Fraction(1, m) for article in ("", "a ", "one ") for word, m in
       (("half", 2), ("third", 3), ("quarter", 4), ("fourth", 4), ("fifth", 5), ("tenth", 10))},
    "la moitié": Fraction(1, 2), "moitié": Fraction(1, 2), "un tiers": Fraction(1, 3), "un quart": Fraction(1, 4),
    "un cinquième": Fraction(1, 5), "un dixième": Fraction(1, 10),
    "la mitad": Fraction(1, 2), "mitad": Fraction(1, 2), "un tercio": Fraction(1, 3), "un cuarto": Fraction(1, 4),
    "un quinto": Fraction(1, 5), "una quinta parte": Fraction(1, 5), "un décimo": Fraction(1, 10), "una décima parte": Fraction(1, 10),
    "die hälfte": Fraction(1, 2), "hälfte": Fraction(1, 2), "ein drittel": Fraction(1, 3), "ein viertel": Fraction(1, 4),
    "ein fünftel": Fraction(1, 5), "ein zehntel": Fraction(1, 10),
})
_MAX_DENOMINATOR = 100

# --------------------------------------------------------------------------- parse


def _normalise(quote: str) -> str:
    """Fold width and case only (fullwidth digits and "％" become ASCII, no-break spaces become blanks)."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", quote)).strip().lower()


def _words_key(body: str) -> str:
    return re.sub(r"[\s\-‐-―]+", " ", body).strip()


def _read_digits(body: str) -> Decimal | str | None:
    """The written decimal, a MALFORMED reason, or None when ``body`` is not one plain decimal.

    A separator followed by exactly three digits after a non-zero integer part ("1,000", "12.500") is refused: it
    reads as a thousands separator in half the investor's languages and as a decimal point in the other half.
    """
    match = _DIGITS_RE.fullmatch(body)
    if match is None:
        return None
    frac = match.group("frac") or ""
    if len(frac) > MAX_DECIMALS:
        return "TOO_MANY_DECIMALS"
    if len(frac) == 3 and int(match.group("int")) != 0:
        return "AMBIGUOUS_SEPARATOR"
    amount = Decimal(f"{match.group('int')}.{frac or '0'}")
    return "OVER_100" if amount > 100 else amount


def _split_mark(work: str) -> tuple[str, bool]:
    match = _MARK_SUFFIX_RE.match(work)
    return (match.group("body").strip(), True) if match else (work, False)


def _single(work: str) -> tuple[str, float | None, str | None] | None:
    """(form, value, reason) when ``work`` is one amount, with or without a percent word, else None."""
    body, marked = _split_mark(work)
    digits = _read_digits(body)
    if isinstance(digits, str):
        return MALFORMED, None, digits
    if digits is not None:
        return (PERCENT, float(digits / 100), None) if marked else (UNIT_UNCLEAR, None, "NO_UNIT")
    words = NUMBER_WORDS.get(_words_key(body))
    if words is None:
        return None
    return (PERCENT_WORDS, float(Decimal(words) / 100), None) if marked else (UNIT_UNCLEAR, None, "NO_UNIT")


def _fraction(work: str) -> tuple[str, float | None, str | None] | None:
    """A spelled fraction or n/m with m <= 100 and n <= m, as a FRACTION; an impossible ratio is MALFORMED."""
    spelled = FRACTION_WORDS.get(_words_key(work))
    if spelled is not None:
        return FRACTION, float(spelled), None
    ratio = _RATIO_RE.fullmatch(work)
    if ratio is None:
        return None
    n, m = int(ratio.group("n")), int(ratio.group("m"))
    if not 0 < m <= _MAX_DENOMINATOR or n > m:
        return MALFORMED, None, "BAD_RATIO"
    return FRACTION, float(Fraction(n, m)), None


def _is_amount(part: str) -> bool:
    body, _ = _split_mark(part.strip())
    return _DIGITS_RE.fullmatch(body) is not None or _words_key(body) in NUMBER_WORDS


def _is_range(work: str) -> bool:
    """Two amounts joined by a dash or a joining word, at any of the joins in the mention."""
    work = _RANGE_LEAD_RE.sub("", work)
    return any(_is_amount(work[:join.start()]) and _is_amount(work[join.end():])
               for join in _RANGE_JOIN_RE.finditer(work) if join.start() > 0)


def _malformed_reason(work: str) -> str:
    if _CURRENCY_RE.search(work):
        return "CURRENCY"
    if _EXPONENT_RE.search(work):
        return "EXPONENT"
    if _SIGN_RE.search(work):
        return "SIGNED"
    if _LETTER_IN_DIGITS_RE.search(work):
        return "LETTER_IN_DIGITS"
    return "NOT_A_QUANTITY"


def parse(mention: str) -> Quantity:
    """Read one amount from the characters the model isolated; anything not plainly one amount carries no value.

    The order matters: an approximation word wins over everything (no value may come from "about 10%"), then a
    fraction, then one plain amount, then a range or alternative; whatever is left is MALFORMED with a reason.
    """
    quote = mention.strip(_TRIM)
    work = _normalise(quote)
    if not work:
        return Quantity(MALFORMED, None, quote, "EMPTY")
    if _HEDGE_RE.search(work):
        return Quantity(HEDGED, None, quote, "HEDGE_WORD")
    work = _BOUND_SUFFIX_RE.sub("", work)
    reading = _fraction(work) or _single(work)
    if reading is not None:
        return Quantity(reading[0], reading[1], quote, reading[2])
    if _is_range(work):
        return Quantity(RANGE, None, quote, "TWO_AMOUNTS")
    return Quantity(MALFORMED, None, quote, _malformed_reason(work))


# --------------------------------------------------------------------------- tokens and ownership


def number_tokens(text: str) -> list[tuple[int, int]]:
    """Offsets of every written number (Unicode digits, fullwidth included; "2,5" and "1.000.000" are one token)."""
    return [match.span() for match in _NUMBER_TOKEN_RE.finditer(text)]


def is_year(token: str) -> bool:
    """A calendar year between 1900 and 2099, so "2022" in "a year like 2022" is not an amount."""
    return _YEAR_RE.fullmatch(unicodedata.normalize("NFKC", token)) is not None


def followed_by_percent(text: str, token_span: tuple[int, int]) -> bool:
    """The number is written as a percentage ("10 %", "10 percent"), so it is an amount whatever the model called it."""
    rest = unicodedata.normalize("NFKC", text[token_span[1]:token_span[1] + 16]).lower()
    return re.match(r"(?:\s*%|\s*(?:percent|per\s+cent|pct|pc|pour\s+cent|pourcent|por\s+ciento|prozent)\b)", rest) is not None


def _word_tokens(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in _WORD_TOKEN_RE.finditer(text)]


def horizon_confirmed(text: str, token_span: tuple[int, int]) -> bool:
    """A time-unit word lies within two words of the number ("next 5 years", "dans 3 ans") and it is no percentage."""
    if followed_by_percent(text, token_span):
        return False
    tokens = _word_tokens(text)
    at = next((i for i, (start, end) in enumerate(tokens) if start <= token_span[0] < end), None)
    if at is None:
        return False
    near = tokens[max(0, at - _HORIZON_DISTANCE):at] + tokens[at + 1:at + 1 + _HORIZON_DISTANCE]
    return any(text[start:end].lower() in TIME_UNITS for start, end in near)


def name_part_confirmed(text: str, token_span: tuple[int, int]) -> bool:
    """The number is part of a name: touching a letter or '&' ("3M", "A320", "S&P500"), or following a word with an
    '&' or an all-capitals word ("S&P 500", "FTSE 100"); and it is no percentage.
    """
    start, end = token_span
    if followed_by_percent(text, token_span):
        return False
    touching = text[max(0, start - 1):start] + text[end:end + 1]
    if any(c.isalpha() or c == "&" for c in touching):
        return True
    previous = text[:start].rsplit(None, 1)
    if not text[max(0, start - 1):start].isspace() or not previous:
        return False
    word = previous[-1]
    letters = [c for c in word if c.isalpha()]
    return "&" in word or (len(letters) >= 2 and all(c.isupper() for c in letters))


# --------------------------------------------------------------------------- hedges


def _containing_sentence(text: str, position: int) -> tuple[int, int]:
    return next(((s, e) for s, e in sentence_spans(text) if s <= position <= e), (0, len(text)))


def hedged_near(text: str, span: tuple[int, int], evidence_span: tuple[int, int]) -> bool:
    """An approximation word sits on the mention, among the 3 words before it, or after it in the same clause.

    The words before stop at the clause's evidence, the sentence and the nearest ``, ; : ! ? ( )`` so that "I care
    about it, max 10%" is not hedged. After the mention, up to the end of the evidence and of the sentence, only the
    phrases that trail an amount count ("10% per company, give or take", "10 % environ"); they are too specific to
    mean anything else. "or less" and "or more" are exact bounds, not hedges.
    """
    start, end = span
    if parse(text[start:end]).form == HEDGED:
        return True
    sentence = _containing_sentence(text, start)
    floor = max(evidence_span[0], sentence[0])
    breaks = [m.end() for m in re.finditer(r"[,;:!?()\n]", text[floor:start])]
    floor += breaks[-1] if breaks else 0
    before = _word_tokens(text[floor:start])[-_HEDGE_WINDOW_TOKENS:]
    if before and _HEDGE_RE.search(_normalise(text[floor + before[0][0]:start])):
        return True
    ceiling = min(evidence_span[1], _containing_sentence(text, max(start, end - 1))[1])
    return _TRAILING_HEDGE_RE.search(_normalise(text[end:max(end, ceiling)])) is not None


# --------------------------------------------------------------------------- dates

_MONTHS = {
    **{name: i for i, names in enumerate((
        ("january", "jan", "janvier", "janv"), ("february", "feb", "février", "fevrier", "févr", "fevr"), ("march", "mar", "mars"),
        ("april", "apr", "avril", "avr"), ("may", "mai"), ("june", "jun", "juin"), ("july", "jul", "juillet", "juil"),
        ("august", "aug", "août", "aout"), ("september", "sep", "sept", "septembre"), ("october", "oct", "octobre"),
        ("november", "nov", "novembre"), ("december", "dec", "décembre", "decembre", "déc")), start=1) for name in names},
}
# Words that make the date a start ("since 2020"); anything else ("before 2020", "in 2020") is not a start date.
_DATE_LEAD_RE = re.compile(r"^(?:(?:ever\s+)?since|from|as\s+of|starting(?:\s+(?:in|from))?|beginning(?:\s+(?:in|from))?|depuis|"
                           r"[aà]\s+partir\s+de|d[eè]s|desde|seit|ab)\s+")
_DATE_TAIL_RE = re.compile(r"\s+(?:onwards?|and\s+later|or\s+later|on)$")
_DATE_RE = re.compile(r"(?:(?P<month>[^\W\d_]+)\.?,?\s+(?:(?:of|de)\s+)?)?(?P<year>(?:19|20)\d\d)")


def parse_date(mention: str) -> str | None:
    """'YYYY-01-01' for a year, 'YYYY-MM-01' for an EN/FR month name and year, else None (the server then asks).

    Only start dates are read: an optional "since / from / depuis ..." before, "onwards" after. A day of the month,
    a second number or an end word ("before", "until") gives None, so no date filter is ever narrower or wider than
    what the investor wrote.
    """
    work = _DATE_TAIL_RE.sub("", _DATE_LEAD_RE.sub("", _normalise(mention.strip(_TRIM))))
    match = _DATE_RE.fullmatch(work)
    if match is None:
        return None
    month = 1
    if match.group("month") is not None:
        if match.group("month") not in _MONTHS:
            return None
        month = _MONTHS[match.group("month")]
    return f"{match.group('year')}-{month:02d}-01"


# --------------------------------------------------------------------------- sentences

# Words after which a full stop does not end a sentence. Initials ("U.S.", "e.g.") are also caught by the
# single-letter rule; they are listed for clarity.
ABBREVIATIONS = frozenset(("u.s", "u.k", "e.g", "i.e", "inc", "corp", "co", "ltd", "st", "mr", "mrs", "ms", "dr", "vs", "approx",
                           "ca", "cf", "jr", "sr"))
_SENTENCE_END_RE = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s)|;(?=\s)")
_INITIALS_RE = re.compile(r"(?:[^\W\d_]\.)*[^\W\d_]")


def _ends_with_abbreviation(text: str, stop: int) -> bool:
    """The word just before the full stop at ``stop`` is one letter or initials ("J.", "U.S.", "e.g.") or a known
    abbreviation ("Inc.", "approx.")."""
    word = re.search(r"\S*$", text[:stop]).group(0).lower().lstrip("\"'([“‘")
    return _INITIALS_RE.fullmatch(word) is not None or word in ABBREVIATIONS


def _breaks(text: str) -> list[tuple[int, int]]:
    """(end of sentence, start of the gap) for each break: a sentence-ending mark, or a newline outside brackets."""
    found: list[tuple[int, int]] = []
    for match in _SENTENCE_END_RE.finditer(text):
        if match.group(0) != ";":
            following = text[match.end():].lstrip()[:1]
            if not (following.isupper() or following.isdigit()):
                continue
            if match.group(0).startswith(".") and _ends_with_abbreviation(text, match.start()):
                continue
        found.append((match.end(), match.end()))
    depth = 0
    for i, char in enumerate(text):
        depth = depth + 1 if char == "(" else max(0, depth - 1) if char == ")" else depth
        if char == "\n" and depth == 0:
            found.append((i, i + 1))
    return sorted(found)


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Offsets of each sentence, blanks trimmed. A break is [.!?] then a blank then a capital or a digit (not after a
    single letter or a known abbreviation), a ';' then a blank, or a newline outside parentheses.

    The ';' and the newline keep the old interpreter's behaviour that a number on the far side of them does not
    belong to the rule ("Not much per company; bonds are 10%").
    """
    spans, begin = [], 0
    for end, resume in _breaks(text) + [(len(text), len(text))]:
        piece = text[begin:end]
        stripped_start = begin + len(piece) - len(piece.lstrip())
        stripped_end = begin + len(piece.rstrip())
        if stripped_end > stripped_start:
            spans.append((stripped_start, stripped_end))
        begin = max(begin, resume)
    return spans
