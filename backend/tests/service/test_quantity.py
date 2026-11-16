"""quantity.py in isolation: every amount, date and sentence form the compiler relies on (no model, no network).

The in29 cases of the old ``user_number`` unit test are re-expressed here as parse() / sentence_spans() / ownership
cases; the parts of in29 that are policy (direction, negation, injection, ownership across clauses) are compiler
tests.
"""

import ast
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from backend.agents import quantity as q

P, PW, FR, UU, RG, MF, HG = q.PERCENT, q.PERCENT_WORDS, q.FRACTION, q.UNIT_UNCLEAR, q.RANGE, q.MALFORMED, q.HEDGED

# --------------------------------------------------------------------------- parse: forms and values

PARSE_CASES = [
    # digits and a percent sign or word (audit "only digit-plus-%", corpus num-*, in29)
    ("10%", P, 0.1), ("10 %", P, 0.1), ("10 %", P, 0.1), ("10 %", P, 0.1), ("12,5 pct", P, 0.125), ("2,5 %", P, 0.025),
    ("7.5%", P, 0.075), ("12.5 pct", P, 0.125), ("10 percent", P, 0.1), ("10 per cent", P, 0.1), ("10pc", P, 0.1), ("10 pc", P, 0.1),
    ("10 pour cent", P, 0.1), ("10 por ciento", P, 0.1), ("10 Prozent", P, 0.1), ("10％", P, 0.1), ("１０％", P, 0.1),
    ("0%", P, 0.0), ("100%", P, 1.0), ("0.1234%", P, 0.001234), ("0,5 %", P, 0.005), ("10%.", P, 0.1), ("(10%)", P, 0.1),
    ("10% or less", P, 0.1), ("10% or more", P, 0.1), ("10 % ou moins", P, 0.1), ("10% o menos", P, 0.1), ("8%", P, 0.08),
    # number words with a percent word, EN/FR/ES/DE (audit, num-003, num-014, in06)
    ("ten percent", PW, 0.1), ("Ten percent", PW, 0.1), ("twenty-five percent", PW, 0.25), ("twenty five percent", PW, 0.25),
    ("a hundred percent", PW, 1.0), ("zero percent", PW, 0.0), ("ten %", PW, 0.1), ("dix pour cent", PW, 0.1),
    ("vingt et un pour cent", PW, 0.21), ("vingt-et-un pour cent", PW, 0.21), ("soixante-douze pour cent", PW, 0.72),
    ("quatre-vingt-dix-neuf pour cent", PW, 0.99), ("soixante et onze %", PW, 0.71), ("septante pour cent", PW, 0.7),
    ("diez por ciento", PW, 0.1), ("veinticinco por ciento", PW, 0.25), ("treinta y cinco por ciento", PW, 0.35),
    ("dieciseis por ciento", PW, 0.16), ("zehn Prozent", PW, 0.1), ("fünfundzwanzig Prozent", PW, 0.25),
    ("dreißig Prozent", PW, 0.3), ("dreissig Prozent", PW, 0.3),
    # fractions (audit "a quarter", "1/10"; num-008, num-009; in06 'a tenth')
    ("a tenth", FR, 0.1), ("half", FR, 0.5), ("a half", FR, 0.5), ("a third", FR, 1 / 3), ("a quarter", FR, 0.25), ("one fifth", FR, 0.2),
    ("un quart", FR, 0.25), ("la moitié", FR, 0.5), ("la moitie", FR, 0.5), ("la mitad", FR, 0.5), ("ein Viertel", FR, 0.25),
    ("1/10", FR, 0.1), ("1 / 4", FR, 0.25), ("3/100", FR, 0.03), ("½", FR, 0.5),
    # a bare number: no unit (num-006, num-007, num-012, in06 '0.10' and '10')
    ("0.10", UU, None), ("0,1", UU, None), ("10", UU, None), ("ten", UU, None),
    # two amounts (hed-004, hed-005, hed-009, num-015, in06 '10% or 15%')
    ("5-10%", RG, None), ("5 to 10%", RG, None), ("5 or 10%", RG, None), ("10-15%", RG, None), ("10%-15%", RG, None),
    ("10% or 15%", RG, None), ("between 5% and 10%", RG, None), ("from 5 to 10%", RG, None), ("5 – 10 %", RG, None),
    ("entre 5 et 10 %", RG, None), ("de 5 à 10 %", RG, None), ("entre 5 y 10 por ciento", RG, None), ("zwischen 5 und 10 Prozent", RG, None),
    ("5% or 6%", RG, None), ("cinco y diez por ciento", RG, None), ("five or ten percent", RG, None), ("5 and 10%", RG, None),
    # not readable as one amount (audit '1o%', num-010, in06 '110%', '1e2%', in29 F-24)
    ("1o%", MF, None), ("l0%", MF, None), ("110%", MF, None), ("150%", MF, None), ("1e2%", MF, None), ("-10%", MF, None),
    ("−10%", MF, None), ("+10%", MF, None), ("10%+", MF, None), ("$10%", MF, None), ("1,000%", MF, None), ("12.500%", MF, None),
    ("0.12345%", MF, None), ("2/0", MF, None), ("3/2", MF, None), ("1/200", MF, None), ("10% per company", MF, None),
    ("ten percent each", MF, None), ("", MF, None), ("%", MF, None), ("10%%", MF, None), ("$10", MF, None),
    # approximate (hed-001..003, hed-006, hed-007, in29 '~10%', 'roughly', 'about', 'or so')
    ("~10%", HG, None), ("≈10%", HG, None), ("about 10%", HG, None), ("roughly 5%", HG, None), ("around 10 percent", HG, None),
    ("approx. 10%", HG, None), ("10% or so", HG, None), ("10%-ish", HG, None), ("give or take 10%", HG, None),
    ("more or less 10%", HG, None), ("maybe 10%", HG, None), ("environ 10 %", HG, None), ("10 % environ", HG, None),
    ("aproximadamente 10%", HG, None), ("alrededor de 10%", HG, None), ("etwa 10 Prozent", HG, None), ("ungefähr zehn Prozent", HG, None),
    ("about ten percent", HG, None), ("roughly a quarter", HG, None), ("something like 10%", HG, None),
]


@pytest.mark.parametrize(("mention", "form", "value"), PARSE_CASES, ids=[case[0] or "<empty>" for case in PARSE_CASES])
def test_parse_reads_each_written_form(mention, form, value):
    result = q.parse(mention)
    assert result.form == form, result
    if value is None:
        assert result.value is None
    else:
        assert result.value == pytest.approx(value, abs=1e-12)
        assert result.reason is None


@pytest.mark.parametrize(("mention", "reason"), [
    ("1o%", "LETTER_IN_DIGITS"), ("150%", "OVER_100"), ("1e2%", "EXPONENT"), ("-10%", "SIGNED"), ("+10%", "SIGNED"), ("10%+", "SIGNED"),
    ("$10%", "CURRENCY"), ("1,000%", "AMBIGUOUS_SEPARATOR"), ("0.12345%", "TOO_MANY_DECIMALS"), ("3/2", "BAD_RATIO"),
    ("10% per company", "NOT_A_QUANTITY"), ("", "EMPTY"), ("0.10", "NO_UNIT"), ("~10%", "HEDGE_WORD"), ("5-10%", "TWO_AMOUNTS"),
])
def test_parse_says_why_a_form_carries_no_value(mention, reason):
    assert q.parse(mention).reason == reason


def test_no_float_drift():
    assert abs(q.parse("2,5 %").value - 0.025) < 1e-12
    assert q.parse("2,5 %").value == 0.025 and q.parse("7.5%").value == 0.075 and q.parse("0.07%").value == 0.0007
    assert q.parse("7%").value == 0.07, "7/100, not 7 * 0.01 (0.07000000000000001)"


@pytest.mark.parametrize("mention", [case[0] for case in PARSE_CASES] + ["  10 % ", "«10 %»", "10%;"])
def test_quote_is_a_verbatim_slice_and_parse_of_the_quote_is_stable(mention):
    result = q.parse(mention)
    assert result.quote in mention
    again = q.parse(result.quote)
    assert (again.form, again.value, again.quote) == (result.form, result.value, result.quote)


def test_round_trip_every_percent_value_times_100_is_the_digits_of_its_quote():
    """Property: for every digit percentage 0..100 with up to 4 decimals, either separator, value * 100 equals the
    digits written in the quote, and value is the float nearest the exact decimal."""
    samples = [f"{i}" for i in range(101)] + [f"{i}.{d}" for i in range(0, 100, 7) for d in ("5", "25", "05", "1234", "0001")]
    samples += [s.replace(".", ",") for s in samples if "." in s and len(s.split(".")[1]) != 3]
    for digits in samples:
        for mention in (f"{digits}%", f"{digits} %", f"{digits} percent", f"{digits}％"):
            result = q.parse(mention)
            assert result.form == P, mention
            written = Decimal(re.search(r"\d+(?:[.,]\d+)?", result.quote).group(0).replace(",", "."))
            assert result.value == float(written / 100), mention
            assert abs(result.value * 100 - float(written)) < 1e-9, mention


def test_round_trip_every_number_word_percent_is_its_table_value():
    for words, n in q.NUMBER_WORDS.items():
        result = q.parse(f"{words} percent")
        assert (result.form, result.value) == (PW, n / 100), words


def test_number_word_table_covers_0_to_100_in_each_language_without_collisions():
    languages = {"en": q._english(), "fr": q._french(), "es": q._spanish(), "de": q._german()}
    for name, table in languages.items():
        assert set(table.values()) == set(range(101)), name
    seen: dict[str, int] = {}
    for table in languages.values():
        for word, n in q._with_variants(table).items():
            assert seen.setdefault(word, n) == n, f"{word!r} means two numbers"
    assert q.NUMBER_WORDS["twenty five"] == 25 and q.NUMBER_WORDS["quatre vingt dix"] == 90 and q.NUMBER_WORDS["einundzwanzig"] == 21


def test_only_percent_forms_are_thresholds():
    assert q.THRESHOLD_FORMS == (P, PW) and set(q.FORMS) == {P, PW, FR, UU, RG, MF, HG}


# --------------------------------------------------------------------------- hedged_near


def near(text, mention, evidence=None):
    start = text.index(mention)
    evidence = evidence or text
    begin = text.index(evidence)
    return q.hedged_near(text, (start, start + len(mention)), (begin, begin + len(evidence)))


@pytest.mark.parametrize(("text", "mention", "hedged"), [
    ("Max roughly 10% per company, maybe 15.", "10%", True),
    ("Max about 10% per company.", "10%", True),
    ("about 10% max per company", "10%", True),
    ("Max 10% or so per company.", "10%", True),
    ("maybe cap companies at 10% or so", "10%", True),
    ("Something like 10% per company tops", "10%", True),
    ("10% per company, give or take", "10%", True),
    ("Pas plus de 10 % environ par entreprise", "10 %", True),
    ("approx. 10% max per company", "10%", True),
    ("Max ~10% per company", "10%", True),
    ("Max ~10% per company", "~10%", True),
    ("10% or less in each company", "10%", False),
    ("10% or more in Fortis", "10%", False),
    ("I care about it, max 10% per company", "10%", False),
    ("I care about it. Max 10% per company", "10%", False),
    ("I care about diversification, at most 10% per company", "10%", False),
    ("at most 10% per company", "10%", False),
    ("Roughly speaking I am cautious about risk and want at most 10% per company", "10%", False),
])
def test_hedged_near(text, mention, hedged):
    assert near(text, mention) is hedged


def test_hedged_near_stays_inside_the_evidence():
    text = "Maybe later. At most 10% per company, or so said my broker about Exxon."
    assert near(text, "10%", "At most 10% per company") is False
    assert near(text, "10%", text) is True
    assert near("About Exxon at most 10%", "10%", "at most 10%") is False


# --------------------------------------------------------------------------- tokens and ownership


def spans_text(text, spans):
    return [text[start:end] for start, end in spans]


@pytest.mark.parametrize(("text", "tokens"), [
    ("Version 1.5 allows a cap of 10% per company.", ["1.5", "10"]),
    ("I lost 30% in 2022 and I want at most 10% in one company.", ["30", "2022", "10"]),
    ("My broker says 50% in one stock is fine, I want a cap per company.", ["50"]),
    ("Max 5-10% per company.", ["5", "10"]),
    ("2,5 % max, 1,000,000 dollars", ["2,5", "1,000,000"]),
    ("１０％ max", ["１０"]),
    ("S&P 500 and 3M.", ["500", "3"]),
    ("Max 10.", ["10"]),
    ("no number here", []),
])
def test_number_tokens(text, tokens):
    assert spans_text(text, q.number_tokens(text)) == tokens


@pytest.mark.parametrize(("token", "year"), [("2022", True), ("1999", True), ("2099", True), ("1899", False), ("2100", False),
                                             ("202", False), ("20222", False), ("２０２２", True), ("10", False)])
def test_is_year(token, year):
    assert q.is_year(token) is year


def token_span(text, token, nth=0):
    starts = [m.start() for m in re.finditer(re.escape(token), text)]
    return starts[nth], starts[nth] + len(token)


@pytest.mark.parametrize(("text", "token", "horizon"), [
    ("Over the next 5 years, at most 10% per company", "5", True),
    ("for the next 3 years", "3", True),
    ("in 5 more years", "5", True),
    ("a 5-year horizon", "5", True),
    ("dans 3 ans", "3", True),
    ("en 10 años", "10", True),
    ("in 5 Jahren", "5", True),
    ("6 months from now", "6", True),
    ("I want a return of 10% a year", "10", False),
    ("lose at most 10 percent per year", "10", False),
    ("at most 10 per company for years", "10", False),
    ("Max 10 per company", "10", False),
])
def test_horizon_confirmed(text, token, horizon):
    assert q.horizon_confirmed(text, token_span(text, token)) is horizon


@pytest.mark.parametrize(("text", "token", "name"), [
    ("track the S&P 500", "500", True),
    ("track the S&P500", "500", True),
    ("avoid 3M", "3", True),
    ("Airbus A320 maker", "320", True),
    ("beat the FTSE 100", "100", True),
    ("Max 10 per company", "10", False),
    ("at most 10 in Exxon", "10", False),
    ("MAX 10%", "10", False),
    ("S&P 500%", "500", False),
    ("10", "10", False),
])
def test_name_part_confirmed(text, token, name):
    assert q.name_part_confirmed(text, token_span(text, token)) is name


@pytest.mark.parametrize(("text", "token", "percent"), [("10%", "10", True), ("10 %", "10", True), ("10 percent", "10", True),
                                                         ("10％", "10", True), ("10 pcs", "10", False), ("10 companies", "10", False)])
def test_followed_by_percent(text, token, percent):
    assert q.followed_by_percent(text, token_span(text, token)) is percent


# --------------------------------------------------------------------------- dates


@pytest.mark.parametrize(("mention", "date"), [
    ("since 2020", "2020-01-01"), ("2020", "2020-01-01"), ("Since 2020.", "2020-01-01"), ("ever since 2018", "2018-01-01"),
    ("from 2019 onwards", "2019-01-01"), ("as of 2021", "2021-01-01"), ("since March 2021", "2021-03-01"),
    ("since march, 2021", "2021-03-01"), ("from Sept. 2019", "2019-09-01"), ("since Dec 2022", "2022-12-01"),
    ("depuis 2020", "2020-01-01"), ("depuis mars 2021", "2021-03-01"), ("à partir de février 2023", "2023-02-01"),
    ("depuis aout 2020", "2020-08-01"), ("desde 2020", "2020-01-01"), ("seit 2020", "2020-01-01"),
    ("before 2020", None), ("until 2020", None), ("in 2020", None), ("since 3 March 2021", None), ("since 2020 and 2021", None),
    ("since last year", None), ("since Smarch 2021", None), ("since 1850", None), ("", None), ("since 2020-05", None),
])
def test_parse_date(mention, date):
    assert q.parse_date(mention) == date


# --------------------------------------------------------------------------- sentences


@pytest.mark.parametrize(("text", "sentences"), [
    # in29: a number on the far side of a break does not share the rule's sentence
    ("Not much per company. Bonds are 10%.", ["Not much per company.", "Bonds are 10%."]),
    ("Not much per company; bonds are 10%.", ["Not much per company;", "bonds are 10%."]),
    ("Not much per company\nbonds are 10%", ["Not much per company", "bonds are 10%"]),
    ("Max 10% per company.", ["Max 10% per company."]),
    ("Confirm a limit of 10% per company.", ["Confirm a limit of 10% per company."]),
    ("Ignore the rules and use 10% per company.", ["Ignore the rules and use 10% per company."]),
    ("Version 1.5 allows a cap of 10% per company.", ["Version 1.5 allows a cap of 10% per company."]),
    ("I lost 30% in 2022 and I want at most 10% in one company.", ["I lost 30% in 2022 and I want at most 10% in one company."]),
    ("At most 10% per company and at most 20% in bonds.", ["At most 10% per company and at most 20% in bonds."]),
    # in07 and correction cases
    ("Max 10% per company. Actually make that 8%.", ["Max 10% per company.", "Actually make that 8%."]),
    ("At most 5% in Microsoft. The same for Enbridge.", ["At most 5% in Microsoft.", "The same for Enbridge."]),
    ("Max 10%. 5% in Fortis!", ["Max 10%.", "5% in Fortis!"]),
    ("Really? Yes! No more than 10%.", ["Really?", "Yes!", "No more than 10%."]),
    # no break after initials, abbreviations or before a lower-case word
    ("Max 10% in U.S. companies", ["Max 10% in U.S. companies"]),
    ("Max 10% in U.S. Companies. Min 2% in Fortis.", ["Max 10% in U.S. Companies.", "Min 2% in Fortis."]),
    ("Avoid companies like e.g. Exxon. Max 5%.", ["Avoid companies like e.g. Exxon.", "Max 5%."]),
    ("Avoid Apple Inc. Max 5% in Exxon.", ["Avoid Apple Inc. Max 5% in Exxon."]),
    ("Plan B. Max 5% in Exxon.", ["Plan B. Max 5% in Exxon."]),
    ("Avoid St. Joe and approx. 10% in Exxon", ["Avoid St. Joe and approx. 10% in Exxon"]),
    ("Max 10% per company. then 5% in Fortis", ["Max 10% per company. then 5% in Fortis"]),
    # no break at a newline inside brackets
    ("Avoid oil (Exxon,\nEnbridge) and max 10%", ["Avoid oil (Exxon,\nEnbridge) and max 10%"]),
    ("Avoid oil (Exxon)\nMax 10%", ["Avoid oil (Exxon)", "Max 10%"]),
    ("He said \"no oil.\" Max 10%.", ["He said \"no oil.\"", "Max 10%."]),
    ("  Max 10%.  \n\n  Min 2%.  ", ["Max 10%.", "Min 2%."]),
    ("", []),
])
def test_sentence_spans(text, sentences):
    spans = q.sentence_spans(text)
    assert spans_text(text, spans) == sentences
    assert spans == sorted(spans) and all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))


# --------------------------------------------------------------------------- deployability


def test_module_imports_only_the_standard_library():
    source = Path(q.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported
