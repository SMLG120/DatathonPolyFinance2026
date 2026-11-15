"""Display formatting for formulas and reasons. Presentation only: no serialized number passes through here.

A printed number is never allowed to contradict the value the result carries:
when the printed digits are not the exact value, the text says so with the
sign "≈" (formulas) or the word "about" (sentences).
"""

from __future__ import annotations

from typing import Optional

EXACT = 1e-12  # a printed number closer than this to the value is the value, for display purposes
APPROX = "≈"


def _digits(value: float, decimals: int) -> tuple[str, bool]:
    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return text, abs(float(text) - value) <= EXACT


def num(value: float) -> str:
    """Up to 9 decimals; prefixed with "≈" when that is not the exact value; negatives in parentheses."""
    text, exact = _digits(value, 9)
    if text.startswith("-"):
        text = f"({text})"
    return text if exact else APPROX + text


def eq(value: float) -> str:
    """The right-hand side of a formula: "= 0.17" when exact, "≈ 0.060667029" when rounded for display."""
    text, exact = _digits(value, 9)
    return f"= {text}" if exact else f"{APPROX} {text}"


def total(values: list) -> str:
    return " + ".join(num(v) for v in values) if values else "0"


def pct(value: float) -> str:
    """A fraction as a percentage with 2 decimals; "about" is added when the 2 decimals are not exact."""
    text, exact = _digits(value * 100, 2)
    text = f"{float(text):.2f}%"
    return text if exact else f"about {text}"


def points(value: float, signed: bool = False) -> str:
    """A difference of fractions in percentage points, with the same "about" rule."""
    text, exact = _digits(value * 100, 2)
    text = f"{float(text):+.2f}" if signed else f"{float(text):.2f}"
    return text if exact else f"about {text}"


def span(measured: Optional[dict]) -> str:
    if measured is None:
        return "not computable"
    if abs(measured["upper"] - measured["lower"]) < 5e-7:
        return pct(measured["lower"])
    return f"between {pct(measured['lower'])} and {pct(measured['upper'])}"
