"""The family as a graph: who is related to whom, estimated lifespans, and what records each source is.

Everything here is derived on the fly from people, claims and sources; nothing is stored.
Estimates (e.g. "born about 1850–1860, from children's births") are labelled as estimates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import placenorm
from .db import rows

# ------------------------------------------------------------------ what kind of record is a source?

US_STATE_NAMES = set(placenorm.US_STATES.values())


def classify_source(title: str | None, url: str | None = None, page_ref: str | None = None) -> dict:
    """Return {kind, year, label}. kind is one of: census, state_census, birth, baptism, marriage, death, burial, obituary,
    newspaper, immigration, naturalization, emigration, draft_ww1, draft_ww2, military, social_security, directory,
    tree, book, other."""
    t = (title or "").strip()
    low = t.lower()
    m = re.search(r"\b(1[789]\d0)\b[^,]*(?:united states|u\.s\.|us|federal)[^,]*census", low) or \
        re.search(r"(?:united states|u\.s\.|us|federal) (?:federal )?census,? (1[789]\d0)\b", low)
    if m and "state census" not in low:
        return {"kind": "census", "year": int(m.group(1)), "label": f"{m.group(1)} U.S. census"}
    if "census" in low and ("state" in low or any(s.lower() in low for s in US_STATE_NAMES)) and "federal" not in low:
        y = re.findall(r"\b(1[789]\d\d)\b", low)
        return {"kind": "state_census", "year": int(y[0]) if len(y) == 1 else None, "label": t}
    if "census" in low:
        y = re.findall(r"\b(1[789]\d\d)\b", low)
        return {"kind": "census", "year": int(y[0]) if len(y) == 1 else None, "label": t}
    rules = [
        ("draft_ww1", r"world war i\b|wwi\b|1917-1918|1917–1918"), ("draft_ww2", r"world war ii|wwii|1940-1947|old man's draft"),
        ("military", r"military|army|navy|marine|enlist|veteran|pension|casualt|civil war|revolution"),
        ("social_security", r"social security"),
        ("naturalization", r"naturali[sz]ation|citizenship|declaration of intention"),
        ("emigration", r"emigra|utvandr|emigrant"),
        ("immigration", r"passenger|immigra|arriving|arrival|crew list|castle garden|ellis island"),
        ("vital", r"vital records|vital extracts|town and vital|vital statistics|town records"),
        ("obituary", r"obituar"),
        ("burial", r"find a grave|findagrave|cemeter|burial|grave|headstone|interment|funeral"),
        ("death", r"death|deaths|died"),
        ("marriage", r"marriage|married|wedding"),
        ("baptism", r"baptism|christening|baptisms|church record|parish|kyrkobok|husförhör"),
        ("birth", r"birth"),
        ("directory", r"director(y|ies)"),
        ("newspaper", r"newspaper|sentinel|telegram|gazette|herald|times|tribune|journal|republican|courier|daily|weekly|newspapers\.com"),
        ("tree", r"family tree|ancestry family trees|family data collection|one world tree|world family tree|pedigree"),
        ("book", r"history of|genealog|biographical|descendants|annals|roster"),
    ]
    for kind, pat in rules:
        if re.search(pat, low):
            if kind in ("newspaper",) and re.search(r"obituar", (page_ref or "").lower()):
                kind = "obituary"
            return {"kind": kind, "year": None, "label": t}
    if url and "newspapers.com" in url:
        return {"kind": "obituary" if "obituar" in (url + (page_ref or "")).lower() else "newspaper", "year": None, "label": t}
    if url and "findagrave" in url:
        return {"kind": "burial", "year": None, "label": t}
    return {"kind": "other", "year": None, "label": t}


# ------------------------------------------------------------------ people and relationships

@dataclass
class Event:
    claim_id: str
    type: str
    date_text: str | None
    year_from: int | None
    year_to: int | None
    place: placenorm.Place
    status: str
    sources: list = field(default_factory=list)   # [{id, title, url, kind, year, page_ref}]
    value: str | None = None

    @property
    def year(self) -> int | None:
        if self.year_from is None:
            return None
        return self.year_from if self.year_to in (None, self.year_from) else (self.year_from + self.year_to) // 2


@dataclass
class Person:
    id: str
    name: str
    sex: str | None
    living: str
    givens: list = field(default_factory=list)
    surnames: list = field(default_factory=list)      # birth surname first
    married_surnames: list = field(default_factory=list)
    events: list = field(default_factory=list)
    parents: list = field(default_factory=list)
    children: list = field(default_factory=list)
    spouses: list = field(default_factory=list)
    sources: dict = field(default_factory=dict)       # source_id -> source info (deduped)

    def ev(self, *types) -> list:
        return [e for e in self.events if e.type in types and e.status != "rejected"]


class Family:
    def __init__(self, project_id: str, people: dict):
        self.project_id = project_id
        self.people: dict[str, Person] = people
        self._life: dict = {}

    def get(self, pid) -> Person | None:
        return self.people.get(pid)

    # ---- lifespans
    def birth(self, pid, _depth=0) -> dict | None:
        """{lo, hi, estimated, basis}"""
        key = ("b", pid)
        if key in self._life:
            return self._life[key]
        self._life[key] = None   # guard against cycles
        p = self.people[pid]
        out = None
        bs = [e for e in p.ev("birth", "baptism") if e.year_from is not None]
        if bs and max(e.year_to or e.year_from for e in bs) - min(e.year_from for e in bs) > 8:
            # Conflicting birth claims: trust the ones with the most sources
            top = max(len(e.sources) for e in bs)
            bs = [e for e in bs if len(e.sources) == top]
        if bs:
            lo = min(e.year_from for e in bs)
            hi = max(e.year_to or e.year_from for e in bs)
            out = {"lo": lo, "hi": hi, "estimated": False, "basis": "recorded birth" if len(bs) == 1 else "recorded births (they differ)" if hi - lo > 2 else "recorded birth"}
        elif _depth < 2:
            cands = []
            for c in p.children:
                cb = self.birth(c, _depth + 1)
                if cb and not cb["estimated"]:
                    cands.append((cb["lo"] - 45, cb["hi"] - 16, "children's births"))
            for s in p.spouses:
                sb = self.birth(s, _depth + 1)
                if sb and not sb["estimated"]:
                    cands.append((sb["lo"] - 12, sb["hi"] + 12, "spouse's birth"))
            for e in p.ev("marriage"):
                if e.year_from:
                    cands.append((e.year_from - 45, e.year_from - 15, "marriage"))
            for pa in p.parents:
                pb = self.birth(pa, _depth + 1)
                if pb and not pb["estimated"]:
                    cands.append((pb["lo"] + 15, pb["hi"] + 48, "parents' births"))
            firsts = [e.year_from for e in p.events if e.year_from and e.type not in ("birth", "baptism")]
            if cands:
                lo = max(c[0] for c in cands)
                hi = min(c[1] for c in cands)
                if firsts:
                    hi = min(hi, min(firsts))
                if lo <= hi:
                    out = {"lo": lo, "hi": hi, "estimated": True, "basis": "estimated from " + ", ".join(dict.fromkeys(c[2] for c in cands))}
            elif firsts:
                out = {"lo": min(firsts) - 60, "hi": min(firsts), "estimated": True, "basis": "estimated: born before the earliest recorded event"}
        self._life[key] = out
        return out

    def death(self, pid) -> dict | None:
        p = self.people[pid]
        ds = [e for e in p.ev("death", "burial") if e.year_from is not None]
        if ds:
            return {"lo": min(e.year_from for e in ds), "hi": max(e.year_to or e.year_from for e in ds), "estimated": False}
        return None

    def last_seen(self, pid) -> int | None:
        ys = [e.year_to or e.year_from for e in self.people[pid].events if e.year_from]
        return max(ys) if ys else None

    def alive_in(self, pid, year: int) -> str:
        """'yes' | 'maybe' | 'no'"""
        b = self.birth(pid)
        d = self.death(pid)
        if b and year < b["lo"]:
            return "no"
        if d and year > d["hi"]:
            return "no"
        if b and year < b["hi"]:
            return "maybe"
        if d and year > d["lo"]:
            return "maybe"
        if not b:
            return "maybe"
        if not d and year > b["hi"] + 95:
            return "no"
        if not d and year > b["lo"] + 75:
            return "maybe"
        return "yes"

    # ---- places
    def birth_place(self, pid) -> placenorm.Place | None:
        for e in self.people[pid].ev("birth", "baptism"):
            if e.place.raw:
                return e.place
        return None

    def foreign_born(self, pid) -> str | None:
        """Country name if born outside the U.S., else None."""
        bp = self.birth_place(pid)
        if bp and bp.country and bp.country != "United States":
            return bp.country
        return None

    def arrival_year(self, pid) -> dict | None:
        p = self.people[pid]
        im = [e for e in p.ev("immigration", "emigration", "migration") if e.year_from]
        if im:
            return {"year": min(e.year_from for e in im), "basis": "recorded immigration"}
        us = [e.year_from for e in p.events if e.year_from and e.place.is_us and e.type not in ("birth", "baptism")]
        if us:
            return {"year": min(us), "basis": "first record in the U.S.", "upper_bound": True}
        return None

    def residence_near(self, pid, year: int) -> tuple | None:
        """(Place, year, how) of the recorded place nearest to `year` (any event with a place)."""
        p = self.people[pid]
        best = None
        for e in p.events:
            if e.year is None or not e.place.raw or e.type in ("birth", "baptism") and year - e.year > 5:
                continue
            if not (e.place.town or e.place.county or e.place.state):
                continue
            d = abs(e.year - year)
            if best is None or d < best[0]:
                best = (d, e)
        if best:
            return best[1].place, best[1].year, best[1].type
        return None

    def search_surname(self, pid) -> str:
        """Birth surname, or for a wife recorded without one, her husband's surname."""
        p = self.people[pid]
        if p.surnames:
            return p.surnames[0]
        if p.married_surnames:
            return p.married_surnames[0]
        for s in p.spouses:
            if self.people[s].surnames:
                return self.people[s].surnames[0]
        return ""

    def siblings(self, pid) -> list:
        sib = set()
        for pa in self.people[pid].parents:
            sib.update(self.people[pa].children)
        sib.discard(pid)
        return sorted(sib, key=lambda x: (self.birth(x) or {}).get("lo") or 9999)

    def ancestors_depth(self, pid, _seen=None) -> int:
        _seen = _seen or set()
        if pid in _seen:
            return 0
        _seen.add(pid)
        ps = self.people[pid].parents
        return 1 + max((self.ancestors_depth(x, _seen) for x in ps), default=0)

    def default_root(self) -> str | None:
        """The person with the deepest ancestry (usually the tree's home person or a close relative)."""
        if not self.people:
            return None
        def score(pid):
            n, stack, seen = 0, [pid], set()
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                n += 1
                stack.extend(self.people[x].parents)
            return (n, (self.birth(pid) or {}).get("lo") or 0)
        return max(self.people, key=score)

    def summary(self, pid) -> dict:
        p = self.people[pid]
        b, d = self.birth(pid), self.death(pid)
        bp = self.birth_place(pid)
        dp = next((e.place for e in p.ev("death", "burial") if e.place.raw), None)
        return {"id": pid, "name": p.name, "sex": p.sex, "living_status": p.living,
                "birth": _range_label(b), "birth_estimated": bool(b and b["estimated"]), "death": _range_label(d),
                "birth_place": bp.short() if bp else None, "death_place": dp.short() if dp else None,
                "lifespan": _lifespan(b, d, p.living)}


def _range_label(r: dict | None) -> str | None:
    if not r:
        return None
    if r["lo"] == r["hi"]:
        return str(r["lo"])
    if r.get("estimated"):
        return f"{r['lo']}–{r['hi']}"
    return f"{r['lo']}–{r['hi']}"


def _lifespan(b, d, living) -> str:
    def y(r, est_word):
        if not r:
            return ""
        if r["lo"] == r["hi"]:
            return str(r["lo"])
        mid = (r["lo"] + r["hi"]) // 2
        return f"{'c.' if r.get('estimated') or r['hi'] - r['lo'] > 2 else ''}{mid}"
    bs, ds = y(b, "b"), y(d, "d")
    if not bs and not ds:
        return "Living" if living == "living" else ""
    return f"{bs or '?'}–{ds or ('' if living == 'living' else '?')}"


def load(conn, project_id: str) -> Family:
    people: dict[str, Person] = {}
    for r in rows(conn, "SELECT id, display_name, sex, living_status FROM persons WHERE project_id = ?", (project_id,)):
        people[r["id"]] = Person(r["id"], r["display_name"], (r["sex"] or None), r["living_status"])
    for n in rows(conn, """SELECT n.person_id, n.name_type, n.given, n.surname FROM person_names n JOIN persons p ON p.id = n.person_id
                           WHERE p.project_id = ? ORDER BY n.created_at""", (project_id,)):
        p = people.get(n["person_id"])
        if not p:
            continue
        if n["given"] and n["given"] not in p.givens:
            p.givens.append(n["given"])
        if n["surname"]:
            target = p.married_surnames if n["name_type"] == "married" else p.surnames
            if n["surname"] not in target:
                target.append(n["surname"])
    for p in people.values():
        if not p.givens and not p.surnames:
            parts = re.sub(r"[\"“”].*?[\"“”]", "", p.name).split()
            if len(parts) > 1:
                p.givens, p.surnames = [" ".join(parts[:-1])], [parts[-1]]
            elif parts:
                p.givens = parts
    srcs: dict[str, list] = {}
    for s in rows(conn, """SELECT e.claim_id, s.id, s.title, s.url, s.page_ref, s.record_date_text, s.origin FROM claim_evidence e
                           JOIN sources s ON s.id = e.source_id WHERE s.project_id = ?""", (project_id,)):
        info = {"id": s["id"], "title": s["title"], "url": s["url"], "page_ref": s["page_ref"], "origin": s["origin"],
                **{k: v for k, v in classify_source(s["title"], s["url"], s["page_ref"]).items() if k != "label"}}
        srcs.setdefault(s["claim_id"], []).append(info)
    for c in rows(conn, """SELECT c.id, c.person_id, c.claim_type, c.date_text, c.year_from, c.year_to, c.status, c.value_text,
                                  c.related_person_id, c.relationship_type, pl.name AS pname, pl.municipality, pl.county, pl.region, pl.country
                           FROM claims c LEFT JOIN places pl ON pl.id = c.place_id WHERE c.project_id = ?""", (project_id,)):
        p = people.get(c["person_id"])
        if not p:
            continue
        if c["claim_type"] == "relationship":
            if c["status"] == "rejected":
                continue
            o = c["related_person_id"]
            if o not in people:
                continue
            rt = c["relationship_type"]
            if rt == "child":
                _link(people, parent=o, child=p.id)
            elif rt == "parent":
                _link(people, parent=p.id, child=o)
            elif rt == "spouse":
                if o not in p.spouses:
                    p.spouses.append(o)
                if p.id not in people[o].spouses:
                    people[o].spouses.append(p.id)
            continue
        place = placenorm.from_row({"name": c["pname"], "municipality": c["municipality"], "county": c["county"],
                                    "region": c["region"], "country": c["country"]}) if (c["pname"] or c["region"] or c["country"]) else placenorm.Place(raw="")
        ev = Event(c["id"], c["claim_type"], c["date_text"], c["year_from"], c["year_to"], place, c["status"], srcs.get(c["id"], []), c["value_text"])
        p.events.append(ev)
        for s in ev.sources:
            p.sources.setdefault(s["id"], s)
    for p in people.values():
        p.events.sort(key=lambda e: (e.year if e.year is not None else 9999, e.type))
    return Family(project_id, people)


def _link(people, parent: str, child: str):
    if parent not in people[child].parents:
        people[child].parents.append(parent)
    if child not in people[parent].children:
        people[parent].children.append(child)
