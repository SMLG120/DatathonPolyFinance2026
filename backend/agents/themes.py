"""Server-side vocabulary the interpreter agent maps the investor's words onto (standard library only).

Everything in this module is deterministic and written by the server. The model only picks codes from these closed
lists; it never writes a label, a description or a definition that reaches the investor.

* ``THEMES``: values-based wishes ("environmental", "green", "ESG", "ethical", "human rights") for which the data
  snapshot holds no sourced classification. A theme never becomes a rule by itself: it becomes a question whose
  options are the definitions the data *can* check (a fund-reported sector label, the controversy registry, named
  companies) next to the definitions it cannot (a green rating, an ESG score), shown as unsupported.
* ``SECTOR_ALIASES``: everyday words for the fund-reported sector labels ("tech", "banks", "pharma"). Used to accept a
  sector focus ("only tech stocks") the investor wrote in their own words. The label offered is always one of the
  snapshot's own labels.
* ``COMPANY_ALIASES``: common names of companies in the starter universe ("Google" for Alphabet, "RBC" for Royal Bank
  of Canada). Matched against the snapshot's cleaned company names, so an alias only resolves when that company is in
  the data. An alias is a *hint* (it puts the company in front of the model and lets the compiler ground an id on the
  investor's words); it never decides which company a clause is about.
* ``CATALOG_TERMS``: words that are ambiguous whatever the model answers ("oil", "pétrole", "petróleo", "fossil
  fuels"). The server always asks its own question about them.
* Veto lexicons (``DIRECTION_VETO``, ``EACH_WORDS``, ``RESTRICTIVE_WORDS``, ``INJECTION_RE``): small multilingual
  lists the compiler runs ONLY over spans the model already isolated (a direction mention, a scope mention, an
  exclusivity mention, a clause). They can only lower an outcome (a rule becomes a question), never raise one.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------- themes

THEME_CODES = ("ENVIRONMENTAL", "ESG", "SOCIAL")
POLARITIES = ("ONLY", "AVOID", "PREFER")

# theme -> (short noun used in server questions, words that name the theme in the investor's text)
THEMES: dict[str, tuple[str, str]] = {
    "ENVIRONMENTAL": (
        "environmental",
        r"environment(?:al(?:ly)?)?(?:[\s-]friendly)?|eco[\s-]?friendly|ecolog(?:y|ical)|green|climate|carbon|"
        r"clean[\s-]energy|clean[\s-]tech|renewables?|planet|nature|pollut(?:e|es|ing|ion|ers?)|emissions?|net[\s-]zero",
    ),
    "ESG": (
        "ESG or responsible-investing",
        r"esg|sustainab(?:le|ility)|ethical(?:ly)?|responsible|socially[\s-]responsible|sri|impact[\s-]invest\w*|"
        r"values[\s-]based|conscious|moral(?:ly)?",
    ),
    "SOCIAL": (
        "social",
        r"human[\s-]rights?|labou?r[\s-](?:rights?|practices|abuses?)|workers?['’]?\s+rights?|child[\s-]labou?r|"
        r"social(?:ly)?\s+(?:harm\w*|good|impact)|exploit\w*",
    ),
}
THEME_TERM_RE = {code: re.compile(rf"\b(?:{pattern})\b", re.IGNORECASE) for code, (_, pattern) in THEMES.items()}

# Cues that turn a theme word into a request the investor wants checked, looked for just before the theme word in the
# same sentence. Used only to decide whether the server asks a question the model left out (never to draft a rule).
ONLY_CUE_RE = re.compile(r"\b(only|exclusively|solely|purely|strictly|nothing but|nothing except|100\s*%)\b", re.IGNORECASE)
PREFER_CUE_RE = re.compile(r"\b(prefer\w*|favou?r\w*|focus\w*(?:\s+on)?|want|wish|like|looking for|invest\w*\s+in|stick\s+to)\b", re.IGNORECASE)
AVOID_CUE_RE = re.compile(r"\b(avoid\w*|exclud\w*|no|nothing|never|without|stay away from|keep away from|screen\w*\s+out|ban\w*|boycott\w*)\b",
                          re.IGNORECASE)
CUE_WINDOW = 48  # characters before the theme word in which a cue counts
# A noun right after the theme word that belongs to the request ("environmental investments").
TRAILING_NOUN_RE = re.compile(r"\s+(investments?|companies|company|stocks?|shares|holdings?|funds?|portfolio|options|assets|businesses|firms|names)\b",
                              re.IGNORECASE)

# --------------------------------------------------------------------------- sectors

# Everyday words -> the GICS-style sector label the funds report. Applied only to labels present in the snapshot.
SECTOR_ALIASES: dict[str, str] = {
    r"tech|technology|technologies|software|semiconductors?|chips?|chipmakers?": "Information Technology",
    r"technologiques?|technologie|tecnolog[ií]as?|tecnol[oó]gic[oa]s?|logiciels?": "Information Technology",
    r"banques?|bancaires?|financi[eè]res?|bancos?|financier[oa]s?|assureurs?|aseguradoras?": "Financials",
    r"services\s+publics|servicios\s+p[uú]blicos": "Utilities",
    r"sant[ée]|pharmaceutiques?|salud|farmac[eé]uticas?": "Health Care",
    r"industrielles?|industriel(?:le)?s?|industriales?|chemins?\s+de\s+fer|ferrocarriles?": "Industrials",
    r"t[ée]l[ée]coms?|t[ée]l[ée]communications?|telecomunicaciones": "Communication Services",
    r"mat[ée]riaux|mini[eè]res?|mineras?|materiales": "Materials",
    r"immobilier|inmobiliari[oa]s?": "Real Estate",
    r"banks?|banking|financials?|finance|insurers?|insurance|lenders?": "Financials",
    r"énergie|energie|énergétiques?|energía|energia|energéticas?": "Energy",
    r"energy|oil and gas": "Energy",
    r"utilit(?:y|ies)|power companies|electric(?:ity)? companies": "Utilities",
    r"health|health\s*care|healthcare|pharma|pharmaceuticals?|biotech|medical": "Health Care",
    r"industrials?|railways?|railroads?|transport(?:ation)?|airlines?|aerospace": "Industrials",
    r"telecoms?|telecommunications?|media|communications?": "Communication Services",
    r"materials|mining|miners?|chemicals?|metals": "Materials",
    r"real\s+estate|reits?|property": "Real Estate",
    r"consumer\s+staples|staples|groceries|grocers?|food(?:\s+companies)?|beverages?": "Consumer Staples",
    r"consumer\s+discretionary|discretionary|retail(?:ers?)?|carmakers?|automakers?|cars": "Consumer Discretionary",
}
_SECTOR_ALIAS_RE = [(re.compile(rf"\b(?:{pattern})\b", re.IGNORECASE), label) for pattern, label in SECTOR_ALIASES.items()]


def sectors_written_in(words: str, labels: list[str]) -> set[str]:
    """Snapshot sector labels the investor wrote in ``words``: the label itself, or an everyday word for it."""
    lowered = words.lower()
    found = {label for label in labels if label.lower() in lowered}
    found.update(label for pattern, label in _SECTOR_ALIAS_RE if label in labels and pattern.search(words))
    return found


# --------------------------------------------------------------------------- companies

# alias (as written, any case) -> the normalised cleaned name it stands for. The name must exist in the snapshot.
COMPANY_ALIASES: dict[str, str] = {
    "google": "alphabet",
    "rbc": "royal bank of canada",
    "royal bank": "royal bank of canada",
    "td bank": "toronto dominion bank",
    "td": "toronto dominion bank",
    "exxonmobil": "exxon mobil",
    "exxon": "exxon mobil",
    "jp morgan": "jpmorgan chase",
    "jpmorgan": "jpmorgan chase",
    "j j": "johnson johnson",
    "j and j": "johnson johnson",
    "p g": "procter gamble",
    "procter and gamble": "procter gamble",
    "cn rail": "canadian national railway",
    "cnrl": "canadian natural resources",
    "couche tard": "alimentation couche tard",
    "circle k": "alimentation couche tard",
    "manulife": "manulife financial",
    "nvidia": "nvidia",
}


def sector_mentions(text: str, labels: list[str]) -> list[tuple[int, int, str]]:
    """Where the investor's text names a snapshot sector label (the label or an everyday word): (start, end, label)."""
    found = []
    for label in labels:
        for match in re.finditer(rf"\b{re.escape(label)}\b", text, re.IGNORECASE):
            found.append((match.start(), match.end(), label))
    for pattern, label in _SECTOR_ALIAS_RE:
        if label in labels:
            found.extend((match.start(), match.end(), label) for match in pattern.finditer(text))
    return sorted(set(found))


# --------------------------------------------------------------------------- catalog

# Words the server always asks about (the oil question), whatever the model answers. A word here never drafts a rule.
CATALOG_TERMS = (
    r"oil|petroleum|fossil\s+fuels?|fossil",
    r"p[ée]trole|p[ée]troli(?:er|[eè]re)s?|fossiles?|combustibles\s+fossiles|[ée]nergies\s+fossiles",
    r"petr[oó]leo|petroler[oa]s?|f[oó]siles?|combustibles\s+f[oó]siles",
)
CATALOG_RE = re.compile(rf"\b(?:{'|'.join(CATALOG_TERMS)})\b", re.IGNORECASE)

# --------------------------------------------------------------------------- veto lexicons (downgrade only)

# Opposite-direction words, looked for inside the model's direction_mention only. A clause read as AT_MOST whose own
# direction words say "at least" (or the reverse) is asked about, never drafted.
DIRECTION_VETO: dict[str, re.Pattern[str]] = {
    "AT_MOST": re.compile(r"\b(?:at\s+least|no\s+less\s+than|not\s+less\s+than|no\s+fewer\s+than|minimum|min|floor|"
                          r"au\s+moins|pas\s+moins\s+de|minimale?|al\s+menos|no\s+menos\s+de|como\s+m[ií]nimo|m[ií]nimo|"
                          r"mindestens|wenigstens)\b", re.IGNORECASE),
    "AT_LEAST": re.compile(r"\b(?:at\s+most|no\s+more\s+than|not\s+more\s+than|maximum|max|cap(?:ped)?|ceiling|up\s+to|"
                           r"au\s+plus|pas\s+plus\s+de|maximale?|jusqu['’]\s*[àa]|como\s+m[aá]ximo|m[aá]ximo|no\s+m[aá]s\s+de|"
                           r"h[öo]chstens|maximal)\b", re.IGNORECASE),
}

# "Each" cues in a scope mention: a per-company amount on a rule the engine measures as a total (controversy).
EACH_WORDS = re.compile(r"\b(?:each|per|every|apiece|chaque|par|chacune?|cada|por|je|jede[rsn]?|pro)\b", re.IGNORECASE)

# Words that make a sector wish exclusive ("only tech"): required inside exclusivity_mention before the server drafts
# the exclusion of every other sector. "Focus on" and "prefer" are not here on purpose.
RESTRICTIVE_WORDS = re.compile(r"\b(?:only|just|exclusively|nothing\s+but|nothing\s+else|solely|"
                               r"seulement|uniquement|que|rien\s+d['’]autre|solo|s[oó]lo|solamente|[uú]nicamente|nur|ausschlie[sß]lich)\b",
                               re.IGNORECASE)

# Wording addressed to the system rather than about the portfolio. A clause whose evidence overlaps a segment holding
# one of these (segments end at . ! ? ; : or a newline, so "Please confirm: at most 10%" keeps its number) gets no
# number. "Set a limit of 10%" is how investors talk about their own rules, so "limit" is not a target of "set".
INJECTION_RE = re.compile(
    r"\b(?:ignore\w*|disregard\w*|forget|override\w*|bypass\w*|instructions?|instrucciones|prompt|system|syst[eè]me|sistema|assistant|"
    r"confirm\w*|approv\w*|activat\w*|activ[ae]r|valide[rz]|oublie[rz]?|olvida\w*|"
    r"set\s+(?:the\s+|my\s+|a\s+|every\s+|all\s+)?(?:status|threshold|rule)s?|you\s+(?:must|should|are|will)|pretend|jailbreak)\b",
    re.IGNORECASE)
