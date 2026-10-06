"""GEDCOM date expressions → qualifier + search window. The original text is always kept verbatim."""
from __future__ import annotations

import re

from ..dates import ABOUT_SPREAD, OPEN_SPREAD

CAL_RE = re.compile(r"@#D([A-Z ]+)@\s*")
YEAR = r"(\d{1,4})(?:/(\d{1,2}))?"   # supports dual dating 1749/50
DATE_RE = re.compile(r"(?:(\d{1,2})\s+)?(?:([A-ZÄÖÜÉÈ]{3,9})\.?\s+)?" + YEAR + r"(?:\s*(B\.?C\.?|BCE))?$")


def _year(s: str) -> tuple[int, int] | None:
    s = s.strip()
    m = DATE_RE.match(s)
    if not m:
        return None
    y = int(m.group(3))
    if m.group(5):
        y = -y
    if m.group(4):  # dual dating: 1749/50 → the event may be recorded under either year
        return (y, y + 1)
    return (y, y)


def parse_gedcom_date(text: str | None) -> dict:
    """Return {date_qualifier, year_from, year_to, calendar, phrase, note}."""
    out = {"date_qualifier": "unknown", "year_from": None, "year_to": None, "calendar": None, "phrase": None, "note": None}
    if not text or not text.strip():
        return out
    t = text.strip()
    phrase = re.search(r"\((.*)\)\s*$", t)
    if phrase:
        out["phrase"] = phrase.group(1)
        t = t[: phrase.start()].strip()
    cal = CAL_RE.findall(t.upper())
    if cal:
        out["calendar"] = cal[0].strip().title()
        if out["calendar"] not in ("Gregorian",):
            out["note"] = f"Date is in the {out['calendar']} calendar; the search window is approximate."
    t = CAL_RE.sub("", t.upper()).strip()
    if not t:
        out["note"] = out["note"] or "Date given only as a phrase"
        return out
    # GEDCOM 7 calendar names without escapes
    t = re.sub(r"^(GREGORIAN|JULIAN|HEBREW|FRENCH_R)\s+", "", t)

    def rng(a, b, q):
        out.update(date_qualifier=q, year_from=a, year_to=b)
        return out

    m = re.match(r"^(?:BET|BETWEEN)\s+(.+?)\s+AND\s+(.+)$", t)
    if m:
        a, b = _year(m.group(1)), _year(m.group(2))
        if a and b:
            return rng(min(a[0], b[0]), max(a[1], b[1]), "between")
    m = re.match(r"^FROM\s+(.+?)(?:\s+TO\s+(.+))?$", t)
    if m:
        a = _year(m.group(1))
        b = _year(m.group(2)) if m.group(2) else None
        if a and b:
            return rng(min(a[0], b[0]), max(a[1], b[1]), "between")
        if a:
            return rng(a[0], a[1] + OPEN_SPREAD, "after")
    m = re.match(r"^TO\s+(.+)$", t)
    if m and _year(m.group(1)):
        y = _year(m.group(1))
        return rng(y[0] - OPEN_SPREAD, y[1], "before")
    m = re.match(r"^(BEF|BEFORE)\.?\s+(.+)$", t)
    if m and _year(m.group(2)):
        y = _year(m.group(2))
        return rng(y[0] - OPEN_SPREAD, y[1], "before")
    m = re.match(r"^(AFT|AFTER)\.?\s+(.+)$", t)
    if m and _year(m.group(2)):
        y = _year(m.group(2))
        return rng(y[0], y[1] + OPEN_SPREAD, "after")
    m = re.match(r"^(ABT|ABOUT|CIRCA|CA|C|CAL|EST|INT)\.?\s+(.+)$", t)
    if m and _year(m.group(2)):
        y = _year(m.group(2))
        q = {"CAL": "calculated", "EST": "estimated"}.get(m.group(1), "about")
        if m.group(1) == "INT":
            out["note"] = "Interpreted date (INT): " + (out["phrase"] or "")
            return rng(y[0], y[1], "estimated")
        return rng(y[0] - ABOUT_SPREAD, y[1] + ABOUT_SPREAD, q)
    y = _year(t)
    if y:
        return rng(y[0], y[1], "exact")
    # Free-text ranges as typed into online trees: "1910-1939", "1 Jun 1918-1919"
    m = re.match(r"^(.+?)\s*[-–]\s*(\d{3,4})$", t)
    if m and _year(m.group(1)):
        a = _year(m.group(1))
        b = int(m.group(2))
        out["note"] = "Free-text date range; kept as written"
        return rng(min(a[0], b), max(a[1], b), "between")
    # Unusual word order such as "Jul Abt 1874"
    years = re.findall(r"\b(\d{3,4})\b", t)
    if len(years) == 1:
        y0 = int(years[0])
        words = set(re.findall(r"[A-Z]+", t))
        out["note"] = "Date written in an unusual form; interpreted loosely and kept as written"
        if words & {"ABT", "ABOUT", "CIRCA", "CA", "C", "EST", "CAL"}:
            return rng(y0 - ABOUT_SPREAD, y0 + ABOUT_SPREAD, "about")
        if words & {"BEF", "BEFORE"}:
            return rng(y0 - OPEN_SPREAD, y0, "before")
        if words & {"AFT", "AFTER"}:
            return rng(y0, y0 + OPEN_SPREAD, "after")
        return rng(y0, y0, "estimated")
    out["note"] = "Date could not be interpreted (no year); kept as written"
    return out
