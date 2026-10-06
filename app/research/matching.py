"""Deterministic match checking for search results.

Given what the tree says about a person (names and the forms records use for them, years,
places, relatives) and a found item (title, snippet and — where the archive allows — its full
OCR text), decide how strongly the item appears to mention this person.

Two kinds of error matter:
* False positives (a different person with the same name). Evidence only counts when it is
  *near the name* — a town or relative mentioned elsewhere on a newspaper page says nothing.
  Ages, titles (Mrs./Mr./Rev.) and death notices that contradict the tree are flagged.
  "Strong" needs the full name plus at least one specific corroboration next to it.
* False negatives (the right person written differently). Nicknames and abbreviations
  (Wm, Maggie, Andrew for Anders), surname spelling families, OCR slips one letter off,
  surname-first index order, and "Mrs. <husband's name>" for married women all count.

The score orders results. It is not a probability that the item is about this person.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .. import names as nm, nameequiv

STRONG = "strong"
POSSIBLE = "possible"
WEAK = "weak"

NEAR = 300   # characters either side of the name that count as "near"
_STATES = {"alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida", "georgia", "hawaii",
           "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
           "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york",
           "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota",
           "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming", "united states",
           "district of columbia"}
_CLERGY = re.compile(r"priest|clergy|minister|pastor|reverend|rector|curate|nun|sister of|bishop|missionar|chaplain", re.IGNORECASE)


def fold(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _fold_map(raw: str) -> tuple[str, list]:
    """Folded copy of `raw` (lower-case, no accents, punctuation runs → one space) and, for each folded character, its index in `raw`."""
    out, idx = [], []
    space = True
    for i, ch in enumerate(raw):
        for d in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(d):
                continue
            d = d.lower()
            if "a" <= d <= "z" or "0" <= d <= "9":
                out.append(d)
                idx.append(i)
                space = False
            elif not space:
                out.append(" ")
                idx.append(i)
                space = True
    return "".join(out), idx


def _lev1(a: str, b: str) -> bool:
    """True if a and b differ by exactly one edit."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(b)):
        if a == b[:i] + b[i + 1:]:
            return True
    return False


@dataclass
class Profile:
    givens: list
    surnames: list
    variant_surnames: list
    year_from: int | None
    year_to: int | None
    places: list            # folded place names (towns, counties, states)
    other_names: list = field(default_factory=list)   # folded full names of relatives
    birth: tuple | None = None    # (from, to) years of recorded birth/baptism
    death: tuple | None = None    # (from, to) years of recorded death/burial
    sex: str | None = None        # "M" / "F"
    given_equivs: list = field(default_factory=list)   # folded nicknames / abbreviations / other-language forms
    husband_givens: list = field(default_factory=list)  # for "Mrs. John Smith"
    occupations: list = field(default_factory=list)
    family_surnames: list = field(default_factory=list)  # surnames of the family (for spotting relatives not in the tree)
    birth_estimated: bool = False   # birth range is an estimate (e.g. from children's births), not a recorded date

    @classmethod
    def from_person(cls, person: dict, windows: list | None = None, relatives: list | None = None) -> "Profile":
        ns = nm.person_name_set(person)
        givens = []
        for g in ns["given"]:
            parts = fold(g).split()
            if parts and parts[0] not in givens:
                givens.append(parts[0])
        surnames = [fold(s) for s in ns["surname"] if fold(s)]
        variants = []
        for s in ns["surname"]:
            variants += [fold(v) for v in nameequiv.surname_variants(s) + nm.spelling_variants(s) + nm.ocr_variants(s)]
        equivs = []
        for g in ns["given"][:2]:
            equivs += [fold(x) for x in nameequiv.given_equivalents(g)]
            parts = g.split()
            if len(parts) > 1 and len(parts[1].strip(".")) > 2:
                equivs.append(fold(parts[1]))   # went by the middle name
        yf = yt = None
        places: list = []
        birth = death = None
        occupations = []
        for c in person.get("claims") or []:
            if c.get("status") == "rejected":
                continue
            if c.get("year_from") is not None and c["claim_type"] in ("birth", "baptism"):
                birth = (min(birth[0], c["year_from"]), max(birth[1], c["year_to"] or c["year_from"])) if birth else (c["year_from"], c["year_to"] or c["year_from"])
            if c.get("year_from") is not None and c["claim_type"] in ("death", "burial"):
                death = (min(death[0], c["year_from"]), max(death[1], c["year_to"] or c["year_from"])) if death else (c["year_from"], c["year_to"] or c["year_from"])
            if c.get("year_from") is not None:
                yf = c["year_from"] if yf is None else min(yf, c["year_from"])
            if c.get("year_to") is not None:
                yt = c["year_to"] if yt is None else max(yt, c["year_to"])
            if c["claim_type"] == "occupation" and c.get("value_text"):
                occupations.append(c["value_text"])
            from .. import placenorm
            pl = placenorm.parse(c.get("place_label") or ", ".join(x for x in [c.get("place_municipality"), c.get("place_county"), c.get("place_region")] if x))
            for v in (pl.town, pl.county, pl.state):
                v = fold(v)
                if v and v not in places:
                    places.append(v)
        for w in windows or []:
            if w.get("year_from") is not None:
                yf = w["year_from"] if yf is None else min(yf, w["year_from"])
            if w.get("year_to") is not None:
                yt = w["year_to"] if yt is None else max(yt, w["year_to"])
        sex = (person.get("sex") or "").upper()[:1] or None
        return cls(givens, surnames, [v for v in dict.fromkeys(variants) if v and v not in surnames], yf, yt, places,
                   [fold(r) for r in relatives or [] if fold(r)], birth, death, sex,
                   [e for e in dict.fromkeys(equivs) if e and e not in givens], [], occupations, list(surnames))

    @classmethod
    def from_family(cls, f, pid: str, windows: list | None = None) -> "Profile":
        """Richer profile from the family graph: relatives, married names, estimated dates, all places."""
        p = f.people[pid]
        base = cls.from_person({"names": [{"given": g, "surname": None} for g in p.givens] +
                                         [{"given": None, "surname": s} for s in p.surnames + p.married_surnames],
                                "display_name": p.name, "claims": [], "sex": p.sex}, windows)
        b, d = f.birth(pid), f.death(pid)
        base.birth = (b["lo"], b["hi"]) if b else None
        base.birth_estimated = bool(b and b.get("estimated"))
        base.death = (d["lo"], d["hi"]) if d else None
        ys = [e.year_from for e in p.events if e.year_from] + [e.year_to for e in p.events if e.year_to]
        if b:
            ys.append(b["lo"])
        if d:
            ys.append(d["hi"])
        if ys:
            base.year_from = min(ys + ([base.year_from] if base.year_from else []))
            base.year_to = max(ys + ([base.year_to] if base.year_to else []))
        for e in p.events:
            for v in (e.place.town, e.place.county, e.place.state):
                v = fold(v)
                if v and v not in base.places:
                    base.places.append(v)
            if e.type == "occupation" and e.value:
                base.occupations.append(e.value)
        rel_ids = p.parents + p.spouses + p.children + f.siblings(pid)
        fam_surnames = set(base.surnames)
        for r in rel_ids:
            rp = f.people[r]
            g = fold(rp.givens[0]).split()[0] if rp.givens and fold(rp.givens[0]) else ""
            sn = rp.surnames + rp.married_surnames
            if (rp.sex or "").upper().startswith("F"):
                sn += [x for sp in rp.spouses for x in f.people[sp].surnames[:1]]
            for s in sn[:3]:
                if g and fold(s):
                    base.other_names.append(f"{g} {fold(s)}")
                    fam_surnames.add(fold(s))
        if (p.sex or "").upper().startswith("F"):
            for s in p.spouses:
                sp = f.people[s]
                if sp.givens and fold(sp.givens[0]):
                    base.husband_givens.append(fold(sp.givens[0]).split()[0])
                for sn in sp.surnames[:1]:
                    if fold(sn) and fold(sn) not in base.surnames:
                        base.surnames.append(fold(sn))
        base.family_surnames = sorted(fam_surnames)
        base.other_names = list(dict.fromkeys(base.other_names))
        return base


@dataclass
class MatchResult:
    score: int
    strength: str
    reasons: list
    context: str | None
    mentions: list = field(default_factory=list)   # other people of the family's surname named near the match


def _window_years(text: str) -> list[int]:
    return [int(y) for y in re.findall(r"\b(1[5-9]\d\d|20[0-2]\d)\b", text)]


def _occurrences(p: Profile, text: str) -> list:
    """All places the person's name appears: (start, end, kind, weight, label)."""
    occ = []
    words = set(text.split())
    fuzzy = []
    for s in p.surnames:
        if len(s) >= 6:
            for w in words:
                if w[:1] == s[:1] and w not in p.surnames and w not in p.variant_surnames and _lev1(w, s):
                    fuzzy.append(w)
    surname_forms = [(s, 1.0, None) for s in p.surnames] + [(s, .8, f"spelling variant “{s}”") for s in p.variant_surnames] + \
                    [(s, .7, f"one letter off — “{s}” (OCR or spelling)") for s in fuzzy[:4]]
    given_forms = [(g, 1.0, None) for g in p.givens] + [(g, .85, f"“{g}” for {p.givens[0] if p.givens else 'the given name'}") for g in p.given_equivs]
    for g, gw, glabel in given_forms:
        if not g:
            continue
        for s, sw, slabel in surname_forms:
            if not s:
                continue
            pat = rf"\b{re.escape(g)}(?: [a-z]\b| [a-z]{{2,12}})? {re.escape(s)}\b|\b{re.escape(s)} {re.escape(g)}\b"
            for m in re.finditer(pat, text):
                label = ", ".join(x for x in (glabel, slabel) if x)
                occ.append((m.start(), m.end(), "full", gw * sw, label))
    for hg in p.husband_givens:
        for s, sw, slabel in surname_forms:
            for m in re.finditer(rf"\bmrs {re.escape(hg)}(?: [a-z]\b| [a-z]{{2,12}})? {re.escape(s)}\b", text):
                occ.append((m.start(), m.end(), "full", .9 * sw, f"as “Mrs. {hg.title()} {s.title()}” (her husband's name)"))
    if not occ:
        for g in p.givens[:1]:
            if g and len(g) > 1:
                for s, sw, slabel in surname_forms[:len(p.surnames) + 2]:
                    for m in re.finditer(rf"\b{re.escape(g[0])} {re.escape(s)}\b", text):
                        occ.append((m.start(), m.end(), "initial", sw, slabel))
            if occ:
                break
    if not occ:
        for s, sw, slabel in surname_forms:
            for m in re.finditer(rf"\b{re.escape(s)}\b", text):
                occ.append((m.start(), m.end(), "surname", sw, slabel))
            if occ:
                break
    return occ


def evaluate(p: Profile, title: str | None, snippet: str | None, full_text: str | None, item_date: str | None,
             item_place: str | None) -> MatchResult:
    raw = " \n".join(x for x in [title, snippet, full_text] if x)
    text, idx = _fold_map(raw)
    reasons: list = []
    iy = _window_years(item_date or "")
    life_lo = p.birth[0] if p.birth else None
    life_hi = (p.death[1] + 5 if p.death else (p.birth[1] + 100 if p.birth else None))

    occ = _occurrences(p, text)
    best = None
    for (a, b, kind, w, label) in occ[:60]:
        local, lr, corro, mism = _local(p, raw, text, idx, a, b, iy)
        base = {"full": 45, "initial": 25, "surname": 12}[kind] * w
        sc = base + local
        if best is None or sc > best[0]:
            best = (sc, a, b, kind, w, label, lr, corro, mism)
    score = 0
    mismatch = False
    corroborated = 0
    name_hit = None
    full_name = False
    if best:
        sc, a, b, kind, w, label, lr, corroborated, mismatch = best
        score += sc
        name_hit = text[a:b]
        full_name = kind == "full"
        if kind == "full":
            reasons.append(f"Full name found: “{name_hit}”" + (f" — {label}" if label else ""))
        elif kind == "initial":
            reasons.append(f"Initial and surname found: “{name_hit}”" + (f" — {label}" if label else ""))
        else:
            reasons.append(f"Surname “{name_hit}” found, but not with the given name")
        reasons += lr
        if len(occ) > 1 and kind == "full":
            reasons.append(f"The name appears {len(occ)} times in the text")
    else:
        if p.surnames:
            codes = {nm.soundex(s) for s in p.surnames}
            for wd in set(text.split()):
                if len(wd) > 3 and wd.isalpha() and nm.soundex(wd) in codes:
                    score += 6
                    name_hit = wd
                    reasons.append(f"A similar-sounding name “{wd}” appears (Soundex)")
                    break
        if not name_hit:
            reasons.append("The person's name was not found in the text available to the app")
            score -= 20

    # Item date: within the years being researched, or at least within a plausible lifetime
    if iy:
        y = iy[0]
        if p.year_from is not None and p.year_to is not None and p.year_from - 5 <= y <= p.year_to + 5:
            score += 15
            reasons.append(f"Item dated {item_date}, within the years being researched ({p.year_from}–{p.year_to})")
        elif life_lo is not None and life_lo <= y <= life_hi:
            score += 12
            reasons.append(f"Item dated {item_date}, within the person's plausible lifetime ({life_lo}–{life_hi})")
        elif life_lo is not None and (y < life_lo - 2 or y > life_hi + 30):
            score -= 25
            reasons.append(f"Item dated {item_date}, outside the person's plausible lifetime")
    elif p.year_from is not None and any(p.year_from - 5 <= y <= (life_hi or p.year_to) + 5 for y in _window_years(raw)):
        score += 8
        reasons.append("A year within the person's lifetime appears in the text")

    # Where the item was published / held
    ip = fold(item_place)
    if ip:
        towns = [pl for pl in p.places if pl not in _STATES and re.search(rf"\b{re.escape(pl)}\b", ip)]
        states = [pl for pl in p.places if pl in _STATES and re.search(rf"\b{re.escape(pl)}\b", ip)]
        item_states = [s for s in _STATES if re.search(rf"\b{s}\b", ip)]
        if towns:
            score += 10
            corroborated += 1 if full_name else 0
            reasons.append(f"Published in {towns[0].title()}, where this person is recorded")
        elif states:
            score += 3
        elif item_states and any(pl in _STATES for pl in p.places):
            score -= 5
            reasons.append(f"Published in {item_place} — not a state where this person is recorded")

    context = extract_context(raw, name_hit) if name_hit and best else (extract_context(raw, name_hit) if name_hit else None)
    if best:
        a, b = best[1], best[2]
        ra, rb = idx[a], idx[min(b, len(idx)) - 1] + 1
        lo, hi = (0, len(raw)) if len(raw) <= 1500 else (max(0, ra - 260), min(len(raw), rb + 260))
        context = ("… " if lo > 0 else "") + re.sub(r"\s+", " ", raw[lo:hi]).strip() + (" …" if hi < len(raw) else "")
    mentions = _mentions(p, raw, best, idx) if best else []
    if mentions:
        reasons.append("Also named nearby (same family surname, not in your tree): " + ", ".join(mentions))

    if mismatch and score < 35:
        strength = WEAK
    elif full_name and not mismatch and score >= 70 and corroborated >= (2 if p.birth_estimated else 1):
        strength = STRONG
    elif score >= 35:
        strength = POSSIBLE
    else:
        strength = WEAK
    if full_name and not mismatch and score >= 70 and strength != STRONG:
        reasons.append("Not marked strong: " + ("nothing next to the name (place, relative or age) confirms it is this person" if not corroborated else
                                                "this person's birth year is only estimated, so one matching detail is not enough"))
    return MatchResult(max(int(round(score)), 0), strength, reasons, context, mentions)


def _local(p: Profile, raw: str, text: str, idx: list, a: int, b: int, iy: list):
    """Evidence near one occurrence of the name. Returns (score, reasons, corroborated, mismatch)."""
    sc, reasons, corro, mism = 0, [], 0, False
    win = text[max(0, a - NEAR):b + NEAR]
    # Places near the name
    towns = [pl for pl in p.places if pl not in _STATES and re.search(rf"\b{re.escape(pl)}\b", win)]
    states = [pl for pl in p.places if pl in _STATES and re.search(rf"\b{re.escape(pl)}\b", win)]
    if towns:
        sc += 15 if len(towns) == 1 else 20
        corro += 1
        reasons.append("Near the name: " + ", ".join(t.title() for t in towns[:3]) + " (where this person is recorded)")
    elif states:
        sc += 3
    # Relatives near the name
    rel = [r for r in p.other_names if r and re.search(rf"\b{re.escape(r)}\b", win)]
    if rel:
        sc += 12 if len(rel) == 1 else 20
        corro += 1 if len(rel) == 1 else 2
        reasons.append("A recorded relative is named nearby: " + ", ".join(r.title() for r in rel[:3]))
    # Title right before the name
    before = text[max(0, a - 14):a]
    tm = re.search(r"\b(mrs|miss|mr|rev|father|sister|dr|capt|sgt|widow)\s*$", before)
    if tm and not text[a:b].startswith("mrs "):
        t = tm.group(1)
        if t in ("mrs", "miss", "widow") and p.sex == "M":
            sc -= 30
            mism = True
            reasons.append(f"Called “{t.title()}.” — but this person is a man: a different person")
        elif t == "mr" and p.sex == "F":
            sc -= 30
            mism = True
            reasons.append("Called “Mr.” — but this person is a woman: a different person")
        elif t in ("rev", "father", "sister") and not any(_CLERGY.search(o or "") for o in p.occupations):
            sc -= 15
            reasons.append(f"Described as “{t.title()}” (clergy) — your tree doesn't record this person as clergy, so this may be someone else")
    elif text[a:b].startswith("mrs ") and p.sex == "M":
        mism = True
        sc -= 30
    # Age right after the name (e.g. "Josiah Whitcomb 65 yrs", "Josiah Whitcomb, aged 53")
    ra, rb = idx[a], idx[min(b, len(idx)) - 1] + 1
    after = raw[rb:rb + 45]
    if iy and p.birth and after:
        am = re.match(r"^[\W_]*(?:aged?\s*)?(\d{1,3})\s*(?:[yv][a-z]{0,4}|,|\.|$)", after, re.IGNORECASE) or \
            re.search(r"\baged?\s+(\d{1,3})\b", after[:30], re.IGNORECASE)
        if am:
            age = int(am.group(1))
            implied = iy[0] - age
            if 0 < age < 115:
                if p.birth[0] - 2 <= implied <= p.birth[1] + 2:
                    if p.birth_estimated:
                        sc += 5
                        reasons.append(f"Age {age} in {iy[0]} implies birth about {implied} — within the estimated birth range "
                                       f"({p.birth[0]}–{p.birth[1]}), which is only an estimate")
                    else:
                        sc += 15
                        corro += 1
                        reasons.append(f"Age {age} in {iy[0]} implies birth about {implied}, which fits the recorded birth")
                elif abs(implied - (p.birth[0] + p.birth[1]) / 2) > 6 and not p.birth_estimated:
                    sc -= 30
                    mism = True
                    reasons.append(f"Age {age} in {iy[0]} implies birth about {implied}, which does not fit the recorded birth "
                                   f"({p.birth[0]}–{p.birth[1]}) — probably a different person with the same name")
    # A death or estate notice dated before the recorded death is about someone else (perhaps a relative)
    if iy and p.death and iy[0] < p.death[0] - 1:
        near = (raw[max(0, ra - 40):ra] + " " + after[:40]).lower()
        if re.search(r"\b(estate of|late of|deceased|died|death of|funeral|obituary|in memoriam|the late|administrat|executor|will of)\b", near):
            sc -= 35
            mism = True
            reasons.append(f"This looks like a death or estate notice from {iy[0]}, but this person's death is recorded about {p.death[0]} — "
                           "likely a different person of the same name (possibly a relative worth researching)")
    # Item dated before the person was born
    if iy and p.birth and iy[0] < p.birth[0] - 1:
        mism = True
        sc -= 20
        reasons.append(f"Item dated {iy[0]}, before this person was born")
    return sc, reasons, corro, mism


_NOT_GIVEN = {"father", "mother", "sister", "brother", "rev", "saint", "st", "mount", "mt", "lake", "street", "the", "and", "of", "to", "in", "at",
              "mr", "mrs", "miss", "dr", "capt", "judge", "hon", "gen", "col", "major", "dear", "uncle", "aunt", "widow", "late", "said", "by", "for",
              "with", "from", "north", "south", "east", "west", "new", "old", "fort", "port", "county", "city", "town", "january", "february", "march",
              "april", "may", "june", "july", "august", "september", "october", "november", "december", "monday", "tuesday", "wednesday", "thursday",
              "friday", "saturday", "sunday", "messrs", "company", "co", "bros", "brothers"}
_IRISH_COUNTIES = {"antrim", "armagh", "carlow", "cavan", "clare", "cork", "donegal", "down", "dublin", "fermanagh", "galway", "kerry", "kildare",
                   "kilkenny", "laois", "leitrim", "limerick", "londonderry", "longford", "louth", "mayo", "meath", "monaghan", "offaly", "roscommon",
                   "sligo", "tipperary", "tyrone", "waterford", "westmeath", "wexford", "wicklow"}
_NAME_RE = re.compile(r"\b(?:(Mrs|Mr|Miss|Rev|Dr|Capt)\.?[ \t]+)?([A-Z][a-z]{1,15}(?:[ \t]+[A-Z]\.?)?(?:[ \t]+[A-Z][a-z]{1,15})?)[ \t]+([A-Z][A-Za-z'’]{2,20})\b")


def _mentions(p: Profile, raw: str, best, idx) -> list:
    """Other people with the family's surname named near the match — possible relatives not yet in the tree."""
    a, b = best[1], best[2]
    ra, rb = idx[a], idx[min(b, len(idx)) - 1] + 1
    seg = raw[max(0, ra - NEAR):rb + NEAR]
    fam = set(p.family_surnames or p.surnames) | set(p.variant_surnames[:6])
    known = set(p.other_names) | {f"{g} {s}" for g in p.givens + p.given_equivs for s in p.surnames}
    out = []
    for m in _NAME_RE.finditer(seg):
        title, given, sur = m.group(1), m.group(2), m.group(3)
        if fold(sur) not in fam:
            continue
        first = fold(given).split()[0] if fold(given) else ""
        if first in _NOT_GIVEN or first in p.places or first in _IRISH_COUNTIES:
            continue
        if not first or f"{first} {fold(sur)}" in known or first in p.givens or first in p.given_equivs:
            continue
        if title == "Mrs" and first in p.husband_givens:
            continue
        label = f"{(title + ('' if title == 'Miss' else '.') + ' ') if title else ''}{given} {sur}"
        if label not in out:
            out.append(label)
    return out[:5]


def extract_context(raw: str, needle: str, width: int = 260) -> str | None:
    """Find the (folded) needle in the original text, ignoring case, accents and punctuation; return the surrounding passage as written."""
    loc = _locate(raw or "", needle or "")
    if not loc:
        return None
    start, end = loc
    a, b = max(0, start - width), min(len(raw), end + width)
    out = re.sub(r"\s+", " ", raw[a:b]).strip()
    return ("… " if a > 0 else "") + out + (" …" if b < len(raw) else "")


def _locate(raw: str, needle: str):
    if not raw or not needle:
        return None
    text, idx = _fold_map(raw)
    m = re.search(r"\b" + re.escape(fold(needle)) + r"\b", text)
    if not m:
        return None
    return idx[m.start()], idx[m.end() - 1] + 1


def text_after(raw: str, needle: str, n: int) -> str:
    loc = _locate(raw or "", needle or "")
    return raw[loc[1]:loc[1] + n] if loc else ""


def text_before(raw: str, needle: str, n: int) -> str:
    loc = _locate(raw or "", needle or "")
    return raw[max(0, loc[0] - n):loc[0]] if loc else ""


def dedupe_key(adapter: str, item_id: str | None, url: str | None) -> str:
    return f"{adapter}:{item_id or url or ''}"
