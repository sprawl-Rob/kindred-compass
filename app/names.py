"""Deterministic name-variant suggestions.

Variants are spelling patterns commonly produced by clerks, indexers, and OCR —
they say nothing about a person's ancestry or identity, and the app never infers
ethnicity or origin from a name.
"""
from __future__ import annotations

import re
import unicodedata

# (pattern, replacement) pairs applied one at a time to generate single-edit variants.
SPELLING_RULES: list[tuple[str, str]] = [
    # Most common clerk/indexer variations first (the research planner uses the first few).
    (r"e$", ""), (r"(?<=[bcdgkmnpt])$", "e"), (r"ss$", "s"), (r"(?<!s)s$", "ss"), (r"tt", "t"), (r"ll", "l"), (r"nn", "n"), (r"mm", "m"), (r"rr", "r"),
    (r"(?<=[^aeiou])l(?=[^l])", "ll"), (r"(?<=[aeiou])t(?=[aeiou])", "tt"), (r"ck", "k"), (r"k", "ck"), (r"c(?=[aou])", "k"), (r"k(?=[aou])", "c"),
    (r"ie$", "y"), (r"y$", "ie"), (r"ey$", "y"), (r"y$", "ey"), (r"ei", "ie"), (r"ie", "ei"), (r"ph", "f"), (r"f", "ph"),
    (r"^mc", "mac"), (r"^mac", "mc"), (r"sen$", "son"), (r"son$", "sen"), (r"ou", "ow"), (r"ow", "ou"), (r"z", "s"), (r"s(?=[aeiou])", "z"),
    (r"sch", "sh"), (r"sh", "sch"), (r"w", "v"), (r"v", "w"), (r"j", "y"), (r"y(?=[aeiou])", "j"), (r"aa", "a"), (r"oe", "ö"), (r"ue", "ü"),
    (r"th", "t"),
]
# Characters that OCR and handwriting indexing commonly confuse.
OCR_CONFUSIONS = [("rn", "m"), ("m", "rn"), ("cl", "d"), ("li", "h"), ("u", "n"), ("n", "u"), ("e", "c")]


def strip_accents(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def soundex(name: str) -> str:
    """American Soundex (as used for U.S. census indexes)."""
    s = re.sub(r"[^A-Za-z]", "", strip_accents(name or "")).upper()
    if not s:
        return ""
    codes = {**dict.fromkeys("BFPV", "1"), **dict.fromkeys("CGJKQSXZ", "2"), **dict.fromkeys("DT", "3"),
             "L": "4", **dict.fromkeys("MN", "5"), "R": "6"}
    first, out, last = s[0], [], codes.get(s[0], "")
    for ch in s[1:]:
        code = codes.get(ch, "")
        if code and code != last:
            out.append(code)
        if ch not in "HW":
            last = code
    return (first + "".join(out) + "000")[:4]


def spelling_variants(name: str, limit: int = 12) -> list[str]:
    base = (name or "").strip()
    if not base:
        return []
    low = base.lower()
    seen = {low}
    out: list[str] = []

    def add(v):
        v = v.strip()
        if v and v.lower() not in seen and len(v) > 1:
            seen.add(v.lower())
            out.append(v[:1].upper() + v[1:] if base[:1].isupper() else v)

    folded = strip_accents(base)
    add(folded)
    for pat, rep in SPELLING_RULES:
        if re.search(pat, low):
            add(re.sub(pat, rep, low, count=1))
        if len(out) >= limit:
            break
    return out[:limit]


def ocr_variants(name: str, limit: int = 4) -> list[str]:
    low = (name or "").lower()
    out = []
    for a, b in OCR_CONFUSIONS:
        if a in low:
            v = low.replace(a, b, 1)
            out.append(v[:1].upper() + v[1:])
        if len(out) >= limit:
            break
    return out


def person_name_set(person: dict) -> dict:
    """Collect all recorded names (birth, married, aliases, original-script) for searching."""
    givens, surnames, full = [], [], []
    for n in person.get("names") or []:
        if n.get("given") and n["given"] not in givens:
            givens.append(n["given"])
        if n.get("surname") and n["surname"] not in surnames:
            surnames.append(n["surname"])
        if n.get("full_text") and n["full_text"] not in full:
            full.append(n["full_text"])
    if not givens and not surnames and person.get("display_name"):
        parts = person["display_name"].split()
        if len(parts) > 1:
            givens, surnames = [" ".join(parts[:-1])], [parts[-1]]
        else:
            surnames = parts
    return {"given": givens, "surname": surnames, "full_text": full}


def suggest_for_person(person: dict, already_tried: list[str] | None = None) -> dict:
    """Variants grouped by reason; marks ones the user already tried."""
    tried = set()
    for t in already_tried or []:
        t = (t or "").strip().lower()
        if t:
            tried.add(t)
            tried.update(w.strip(".,;:()\"'“”") for w in t.split())
    names = person_name_set(person)
    groups = []
    recorded = [n for n in names["surname"]] + names["full_text"]
    if len(recorded) > 1:
        groups.append({"reason": "Other recorded names for this person (maiden, married, alias, original script)", "variants": recorded})
    for s in names["surname"][:3]:
        sv = spelling_variants(s)
        if sv:
            groups.append({"reason": f"Spelling variants of “{s}” clerks and indexers often produce", "variants": sv})
        ov = ocr_variants(s)
        if ov:
            groups.append({"reason": f"Handwriting / OCR misreadings of “{s}” (useful for full-text and newspaper search)", "variants": ov})
        code = soundex(s)
        if code:
            groups.append({"reason": f"Soundex code {code} — many U.S. census and immigration indexes group names by Soundex", "variants": [code], "kind": "code"})
    for g in names["given"][:2]:
        initial = g.strip()[:1]
        if initial:
            groups.append({"reason": f"Records often abbreviate given names — try the initial or a nickname for “{g}”",
                           "variants": [f"{initial}.", g.split()[0]] if " " in g else [f"{initial}."]})
    for grp in groups:
        grp["tried"] = [v for v in grp["variants"] if v.lower() in tried]
    return {"names": names, "groups": groups}
