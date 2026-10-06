"""Parse genealogical date phrases into a qualifier and a year range.

The verbatim text is always kept; the year range is only a search window.
Examples:  "1852" → exact 1852–1852;  "abt 1852" → about 1850–1854;
"bef 1880" → before 1860–1879;  "aft 1880" → after 1881–1900;
"bet 1870 and 1875" / "1870-1875" → between;  "1850s" → about 1850–1859;
"12 Mar 1861" → exact 1861;  "" → unknown.
"""
from __future__ import annotations

import re

ABOUT_SPREAD = 2
OPEN_SPREAD = 20

_ABOUT = r"(?:abt\.?|about|approx\.?|approximately|circa|ca\.?|c\.|~|est\.?|estimated|cal\.?|calculated|say)"
_BEF = r"(?:bef\.?|before|by)"
_AFT = r"(?:aft\.?|after|since)"
_YEAR = r"(\d{3,4})"
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{3,4}"


def parse_date(text: str | None) -> dict:
    """Return {date_qualifier, year_from, year_to}."""
    if not text or not text.strip():
        return {"date_qualifier": "unknown", "year_from": None, "year_to": None}
    t = text.strip().lower()

    m = re.search(r"(?:bet\.?|between|from)\s*.*?" + _YEAR + r".*?(?:and|to|-|–)\s*.*?" + _YEAR, t)
    if not m:
        m = re.fullmatch(r"\s*" + _YEAR + r"\s*(?:-|–|to)\s*" + _YEAR + r"\s*", t)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return {"date_qualifier": "between", "year_from": a, "year_to": b}

    m = re.search(r"\b(\d{3})0s\b", t)
    if m:
        y = int(m.group(1)) * 10
        return {"date_qualifier": "about", "year_from": y, "year_to": y + 9}

    m = re.search(_YEAR, t)
    if not m:
        return {"date_qualifier": "unknown", "year_from": None, "year_to": None}
    y = int(m.group(1))

    if re.match(r"\s*" + _BEF + r"\b", t):
        return {"date_qualifier": "before", "year_from": y - OPEN_SPREAD, "year_to": y - (0 if re.search(_MONTH, t) else 1)}
    if re.match(r"\s*" + _AFT + r"\b", t):
        return {"date_qualifier": "after", "year_from": y + (0 if re.search(_MONTH, t) else 1), "year_to": y + OPEN_SPREAD}
    if re.match(r"\s*" + _ABOUT, t):
        q = "calculated" if t.startswith("cal") else "estimated" if t.startswith("est") else "about"
        return {"date_qualifier": q, "year_from": y - ABOUT_SPREAD, "year_to": y + ABOUT_SPREAD}
    return {"date_qualifier": "exact", "year_from": y, "year_to": y}


def window(claims: list[dict]) -> tuple[int | None, int | None]:
    """Union of year ranges of claims that have any."""
    lo = [c["year_from"] for c in claims if c.get("year_from") is not None]
    hi = [c["year_to"] for c in claims if c.get("year_to") is not None]
    return (min(lo) if lo else None, max(hi) if hi else None)


def overlaps(a_from, a_to, b_from, b_to) -> bool:
    if None in (a_from, a_to, b_from, b_to):
        return True  # unknown is not evidence of conflict
    return a_from <= b_to and b_from <= a_to
