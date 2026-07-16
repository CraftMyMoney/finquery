"""Numeric matcher for the eval harness: is the ground-truth number present
in a free-text answer, regardless of formatting?

Handles rupee symbols and prefixes, Western (10,900) and Indian (1,00,812)
digit grouping, decimals, and percents; all values compare as Decimal, so
"10900" == "10,900.00". Known limitation, recorded here on purpose: word
forms like "1.5 lakh" are not expanded. No golden ground truth is written
that way, and the graders read exact rupee figures.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

# A number either comma-grouped (both 10,900 and 1,00,812) or plain (10900),
# with an optional decimal part. Lookarounds keep it from matching inside a
# longer number, so "txn 109003" can never yield 10900; the trailing guard
# only rejects a comma that CONTINUES the number (",5"), not a prose comma
# ("Rs 1,00,000, which...").
_NUMBER = re.compile(
    r"(?<![\d.,])(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?(?!\d|,\d)"
)


def extract_numbers(text: str) -> set[Decimal]:
    """All numbers in the text, commas stripped, as exact Decimals."""
    values: set[Decimal] = set()
    for match in _NUMBER.finditer(text):
        try:
            values.add(Decimal(match.group().replace(",", "")))
        except InvalidOperation:  # pragma: no cover - regex should prevent this
            continue
    return values


def numeric_match(expected: str | int | Decimal, text: str) -> bool:
    """True if the expected value appears anywhere in the answer text.

    Decimal equality is numeric, so an expected "10900.00" matches an answer
    that says "Rs 10,900" and vice versa.
    """
    return Decimal(str(expected)) in extract_numbers(text)


def date_mentioned(iso_date: str, text: str) -> bool:
    """True if the ground-truth date appears in the answer in any common
    rendering: ISO, '20 March 2026', 'March 20, 2026', ordinals, dd/mm/yyyy.
    Same spirit as numeric_match: normalize the comparison, not the model."""
    d = date.fromisoformat(iso_date)
    haystack = text.lower()
    month, mon = d.strftime("%B").lower(), d.strftime("%b").lower()
    day, year = str(d.day), str(d.year)
    if 11 <= d.day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
    candidates = [
        iso_date,
        f"{day} {month} {year}", f"{day} {mon} {year}",
        f"{day}{suffix} {month} {year}", f"{day}{suffix} of {month} {year}",
        f"{month} {day}, {year}", f"{mon} {day}, {year}",
        f"{month} {day} {year}", f"{month} {day}{suffix}, {year}",
        f"{d.day:02d}/{d.month:02d}/{year}", f"{d.day:02d}-{d.month:02d}-{year}",
    ]
    return any(c in haystack for c in candidates)
