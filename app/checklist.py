"""Record checklist: which records should exist for a person, which ones the tree already has,
and where to look for the missing ones.

The expectations are rules of thumb from U.S. and European record-keeping (which censuses named
everyone, who registered for the draft, when Social Security began, …). Every item says *why* it
is expected, and items that depend on uncertain dates are marked "maybe" rather than counted as gaps.
"""
from __future__ import annotations

from . import nameequiv, names as nm, placenorm, searchlinks
from .family import Family

FEDERAL_CENSUS_YEARS = list(range(1790, 1951, 10))
CENSUS_FIELDS = {
    1790: "Head of household only; others are counted by age group and sex.",
    1800: "Head of household only; others are counted by age group and sex.",
    1810: "Head of household only; others are counted by age group and sex.",
    1820: "Head of household only; others counted by age group; foreigners not naturalized are counted.",
    1830: "Head of household only; others are counted by age group and sex.",
    1840: "Head of household only; also names Revolutionary War pensioners.",
    1850: "First census to name everyone: age, sex, occupation, birthplace (state or country).",
    1860: "Everyone named: age, occupation, birthplace, value of real and personal estate.",
    1870: "Everyone named: age, birthplace, whether father/mother were foreign-born, month of birth if born that year.",
    1880: "Relationship to the head of household, marital status, and the birthplaces of each person's father and mother.",
    1890: "Almost entirely destroyed by fire in 1921; only fragments survive (plus a special schedule of Union veterans and widows).",
    1900: "Month and year of birth, years married, number of children born and living (for mothers), year of immigration, naturalization status.",
    1910: "Years married, children born/living, year of immigration, naturalization, mother tongue, Civil War veteran.",
    1920: "Year of immigration and naturalization, mother tongue of the person and parents, home owned or rented.",
    1930: "Age at first marriage, year of immigration, naturalization, veteran status, home value, radio.",
    1940: "Where the person lived in 1935, schooling, income; who gave the information (circled ✓).",
    1950: "Most recent public census; birthplace, occupation, and for some people where they lived a year earlier.",
}
# Surviving name-level state censuses (selected states where they are widely indexed).
STATE_CENSUSES = {
    "Massachusetts": [1855, 1865], "New York": [1855, 1865, 1875, 1892, 1905, 1915, 1925],
    "Iowa": [1885, 1895, 1905, 1915, 1925], "Kansas": [1865, 1875, 1885, 1895, 1905, 1915, 1925],
    "Minnesota": [1865, 1875, 1885, 1895, 1905], "Wisconsin": [1855, 1875, 1885, 1895, 1905],
    "Rhode Island": [1865, 1875, 1885, 1905, 1915, 1925, 1935], "New Jersey": [1885, 1895, 1905, 1915],
    "Nebraska": [1885], "Colorado": [1885], "Florida": [1885, 1935, 1945], "South Dakota": [1905, 1915, 1925, 1935, 1945],
    "North Dakota": [1915, 1925], "Michigan": [1884, 1894],
}

GROUPS = {"parents": "Finding parents", "census": "Census", "vital": "Birth, marriage & death", "migration": "Immigration & citizenship",
          "military": "Military", "other": "Other records"}


def name_forms(f: Family, pid: str) -> dict:
    p = f.people[pid]
    given = p.givens[0] if p.givens else ""
    surname = p.surnames[0] if p.surnames else (p.married_surnames[0] if p.married_surnames else "")
    gv = nameequiv.given_equivalents(given)[:8]
    sv = []
    for s in p.surnames[:2]:
        for v in nameequiv.surname_variants(s) + nm.spelling_variants(s, 6):
            if v.lower() not in (x.lower() for x in sv) and v.lower() != s.lower():
                sv.append(v)
    plain = nameequiv.strip_quoted(given)
    return {"given": plain.split()[0] if plain else "", "given_full": plain, "surname": surname,
            "surnames": p.surnames, "married_surnames": p.married_surnames, "given_variants": gv,
            "surname_variants": sv[:10], "abbreviations": nameequiv.abbreviations(given),
            "soundex": [nm.soundex(s) for s in p.surnames[:2] if s]}


def _age_at(f: Family, pid: str, year: int) -> str | None:
    b = f.birth(pid)
    if not b:
        return None
    lo, hi = year - b["hi"], year - b["lo"]
    lo, hi = max(lo, 0), max(hi, 0)
    return str(lo) if lo == hi else f"{lo}–{hi}"


def _household(f: Family, pid: str, year: int) -> list:
    """Who is likely to be in the same household in `year`."""
    p = f.people[pid]
    b = f.birth(pid)
    age = (year - (b["lo"] + b["hi"]) // 2) if b else None
    out = []
    if age is not None and age < 18:
        for pa in p.parents:
            if f.alive_in(pa, year) != "no":
                out.append({"id": pa, "name": f.people[pa].name, "role": "parent"})
        for s in f.siblings(pid):
            if f.alive_in(s, year) == "yes":
                sb = f.birth(s)
                if sb and year - sb["hi"] < 21:
                    out.append({"id": s, "name": f.people[s].name, "role": "sibling"})
    else:
        for sp in p.spouses:
            marr = [e.year_from for e in p.ev("marriage") if e.year_from]
            if f.alive_in(sp, year) != "no" and (not marr or min(marr) <= year):
                out.append({"id": sp, "name": f.people[sp].name, "role": "spouse"})
        for c in p.children:
            cb = f.birth(c)
            if cb and cb["hi"] <= year and year - cb["lo"] < 21 and f.alive_in(c, year) != "no":
                out.append({"id": c, "name": f.people[c].name, "role": "child"})
    return out[:10]


def _has(p, kinds, year=None, claim_types=None) -> list:
    out = []
    for e in p.events:
        if claim_types and e.type not in claim_types:
            continue
        for s in e.sources:
            if s["kind"] not in kinds:
                continue
            if year is not None and not (s.get("year") == year or (s.get("year") is None and e.year_from == year)):
                continue
            if s not in out:
                out.append(s)
    return out


def surname_at(f: Family, pid: str, year: int) -> str:
    """The surname a woman was probably recorded under in `year` (her husband's after marriage)."""
    p = f.people[pid]
    base = f.search_surname(pid)
    if not (p.sex or "").upper().startswith("F") or not p.spouses:
        return base
    best = None
    for sp in p.spouses:
        sn = f.people[sp].surnames[0] if f.people[sp].surnames else None
        if not sn:
            continue
        marr = [e.year_from for e in p.ev("marriage") if e.year_from]
        kids = [f.birth(c) for c in p.children if c in f.people[sp].children]
        start = min(marr) if marr else (min(k["lo"] for k in kids if k) - 1 if any(kids) else None)
        if start and start <= year and (best is None or start > best[0]):
            best = (start, sn)
    return best[1] if best else base


def _in_us(f: Family, pid: str, year: int) -> str:
    """'yes' | 'maybe' | 'no' — was the person living in the U.S. in this year?"""
    fb = f.foreign_born(pid)
    p = f.people[pid]
    us_evidence = any(e.place.is_us for e in p.events) or any((f.birth_place(c) or placenorm.Place(raw="")).is_us for c in p.children)
    if not us_evidence:
        return "no"   # nothing recorded in the U.S. — don't invent census gaps
    if not fb:
        bp = f.birth_place(pid)
        if bp and bp.is_us:
            return "yes"
        near = f.residence_near(pid, year)
        if near and near[0].is_us:
            return "yes"
        if near and near[0].country and not near[0].is_us:
            return "no"
        return "maybe" if not bp else "yes"
    arr = f.arrival_year(pid)
    if not arr:
        return "maybe"
    if year >= arr["year"]:
        return "yes"
    return "maybe" if arr.get("upper_bound") else "no"


def build(f: Family, pid: str) -> dict:
    p = f.people[pid]
    forms = name_forms(f, pid)
    b, d = f.birth(pid), f.death(pid)
    items: list[dict] = []
    male = (p.sex or "").upper().startswith("M")
    female = (p.sex or "").upper().startswith("F")
    fb = f.foreign_born(pid)
    bp = f.birth_place(pid)
    ctx_base = {"forms": forms, "birth": b, "death": d, "birth_place": bp}

    def add(**kw):
        kw.setdefault("found", [])
        kw.setdefault("status", "found" if kw["found"] else "missing")
        kw.setdefault("priority", 50)
        kw.setdefault("searches", [])
        items.append(kw)

    # ---- censuses
    for y in FEDERAL_CENSUS_YEARS:
        alive = f.alive_in(pid, y)
        if alive == "no":
            continue
        if y > 1950:
            continue
        where = _in_us(f, pid, y)
        if where == "no":
            continue
        age = _age_at(f, pid, y)
        found = _has(p, {"census"}, y)
        near = f.residence_near(pid, y)
        place = near[0] if near else (bp if bp and bp.is_us else None)
        hh = _household(f, pid, y)
        head_only = y < 1850
        status = "found" if found else ("lost" if y == 1890 else "maybe" if alive == "maybe" or where == "maybe" else "missing")
        why = []
        if alive == "yes":
            why.append(f"alive in {y}" + (f" (about {age})" if age else ""))
        else:
            why.append(f"possibly alive in {y}" + (" — birth or death year uncertain" if not b or b["estimated"] else ""))
        if fb:
            arr = f.arrival_year(pid)
            why.append(f"born in {fb}; " + (f"in the U.S. by {arr['year']} ({arr['basis']})" if arr else "arrival year unknown"))
        if head_only:
            parent = next((x for x in hh if x["role"] == "parent"), None)
            note = "Only heads of household are named. " + (f"Look for {parent['name']}'s household." if parent and age and age.split('–')[0].isdigit() and int(age.split('–')[0]) < 16 else "Look for this person as a head of household.")
        else:
            note = None
        ctx = {**ctx_base, "year": y, "place": place, "surname": surname_at(f, pid, y)}
        add(id=f"census-{y}", group="census", title=f"{y} U.S. census", year=y, status=status, found=found,
            why="; ".join(why), tells=CENSUS_FIELDS.get(y), note=note,
            expect={"age": age, "place": place.short() if place else None, "place_basis": f"recorded in {near[1]} ({near[2]})" if near else None,
                    "household": hh},
            priority=(70 if y >= 1850 else 40) - (25 if status == "maybe" else 0),
            searches=searchlinks.census(ctx), auto=searchlinks.auto_census(ctx))
    # Census of Ireland 1901 / 1911 (for people still in Ireland then)
    from .integrations.census import _plan_ireland, irish_county
    irq, _ = _plan_ireland(f, pid)
    if irq:
        county = irq[0].get("place")
        for y in (1901, 1911):
            if not (irq[0]["years"][0] <= y <= irq[0]["years"][1]):
                continue
            found = [s for s in _has(p, {"census"}) if s.get("year") == y or "ireland" in (s.get("title") or "").lower() and str(y) in (s.get("title") or "")]
            ctx = {**ctx_base, "year": y, "county": county}
            add(id=f"census-ireland-{y}", group="census", title=f"{y} census of Ireland", year=y, found=found,
                status="found" if found else ("missing" if f.alive_in(pid, y) == "yes" else "maybe"),
                why=irq[0]["why"], tells="Every person in the household with age, relationship to the head, occupation, county of birth, religion; "
                "1911 adds years married and children born/living.", expect={"age": _age_at(f, pid, y), "place": f"Co. {county}, Ireland" if county else "Ireland",
                                                                            "household": _household(f, pid, y)},
                priority=60, searches=searchlinks.irish_census(ctx), auto={"adapters": ["census_ireland"], "label": "Search the Irish census now (free)"})

    # state censuses
    states = set()
    for e in p.events:
        if e.place.is_us and e.place.state and e.year:
            states.add(e.place.state)
    if bp and bp.is_us and bp.state:
        states.add(bp.state)
    for st in sorted(states):
        for y in STATE_CENSUSES.get(st, []):
            if f.alive_in(pid, y) == "no" or _in_us(f, pid, y) == "no":
                continue
            near = f.residence_near(pid, y)
            if not near or near[0].state != st or abs(near[1] - y) > 12:
                continue
            found = [s for s in _has(p, {"state_census"}) if s.get("year") in (y, None)]
            found = [s for s in found if s.get("year") == y or any(e.year_from == y for e in p.events if s in e.sources)]
            ctx = {**ctx_base, "year": y, "place": near[0], "state": st, "surname": surname_at(f, pid, y)}
            add(id=f"state-census-{st}-{y}", group="census", title=f"{y} {st} state census", year=y, found=found,
                why=f"living in {st} around {y} (recorded {near[0].short()}, {near[1]})", status="found" if found else ("missing" if f.alive_in(pid, y) == "yes" else "maybe"),
                tells="State censuses fill the gaps between federal censuses (and 1890). Fields vary by year.",
                expect={"age": _age_at(f, pid, y), "place": near[0].short(), "household": _household(f, pid, y)},
                priority=45, searches=searchlinks.state_census(ctx))

    # ---- vital records
    bfound = _has(p, {"birth", "baptism", "vital"}, claim_types=("birth", "baptism"))
    by = (b["lo"] + b["hi"]) // 2 if b else None
    add(id="birth", group="vital", title="Birth or baptism record", year=by, found=bfound,
        why=("born " + (bp.short() if bp else "place unknown") + (f", {b['lo'] if b['lo'] == b['hi'] else str(b['lo']) + '–' + str(b['hi'])}" if b else "")),
        tells=searchlinks.birth_hint(bp, by), priority=60 if not p.parents else 45,
        searches=searchlinks.vital({**ctx_base, "event": "birth", "place": bp, "year": by}))
    marr_events = p.ev("marriage")
    for sp in p.spouses or ([None] if marr_events else []):
        evs = [e for e in marr_events] if sp is None else marr_events
        found = _has(p, {"marriage", "vital"}, claim_types=("marriage",))
        my = next((e.year for e in evs if e.year), None)
        mplace = next((e.place for e in evs if e.place.raw), None)
        spn = f.people[sp].name if sp else None
        est = False
        if not my and sp:
            kids = [f.birth(c) for c in p.children]
            kids = [k["lo"] for k in kids if k and not k["estimated"]]
            if kids:
                my, est = min(kids) - 1, True
                if b:
                    my = max(my, b["hi"] + 17)
        add(id=f"marriage-{sp or 'x'}", group="vital", title="Marriage record" + (f" — {spn}" if spn else ""), year=my, found=found,
            why=(f"married {spn}" if spn else "a marriage is recorded") + (f" about {my}" + (" (estimated from the children's births)" if est else "") if my else ""),
            tells=searchlinks.marriage_hint(mplace or (f.residence_near(pid, my)[0] if my and f.residence_near(pid, my) else None), my),
            priority=55 if not p.parents else 40,
            searches=searchlinks.vital({**ctx_base, "event": "marriage", "place": mplace or (f.residence_near(pid, my)[0] if my and f.residence_near(pid, my) else None),
                                        "year": my, "spouse": f.people[sp] if sp else None}))
    dead = d is not None or p.living == "deceased" or (b and b["hi"] < 1925)
    if dead:
        dy = (d["lo"] + d["hi"]) // 2 if d else None
        dplace = next((e.place for e in p.ev("death", "burial") if e.place.raw), None) or (f.residence_near(pid, dy or 9999) or (None,))[0]
        dctx = {**ctx_base, "event": "death", "place": dplace, "year": dy}
        add(id="death", group="vital", title="Death record", year=dy, found=_has(p, {"death", "vital"}, claim_types=("death",)),
            why=("died " + (dplace.short() if dplace else "place unknown") + (f", {dy}" if dy else ", year unknown")),
            tells=searchlinks.death_hint(dplace, dy), priority=55 if not p.parents else 40, searches=searchlinks.vital(dctx))
        if not dy or dy >= 1850:
            add(id="obituary", group="vital", title="Obituary or death notice", year=dy, found=_has(p, {"obituary", "newspaper"}),
                why="newspapers routinely printed death notices" + (f" in {dy}" if dy else ""),
                tells="Obituaries name surviving spouse, children, brothers and sisters (often married sisters by married name), parish, and sometimes birthplace.",
                priority=50, searches=searchlinks.obituary(dctx), auto=searchlinks.auto_newspaper(dctx))
        add(id="burial", group="vital", title="Burial / grave", year=dy, found=_has(p, {"burial"}),
            why="a burial place is usually recorded", tells="Gravestones and cemetery records give dates and often show family plots (who is buried together).",
            priority=30, searches=searchlinks.burial(dctx))

    # ---- migration
    if fb:
        arr = f.arrival_year(pid)
        ay = arr["year"] if arr else None
        us_states = [e.place.state for e in p.events if e.place.is_us and e.place.state]
        mctx = {**ctx_base, "year": ay, "country": fb, "us_state": us_states[0] if us_states else None}
        add(id="immigration", group="migration", title=f"Passenger list (from {fb})", year=ay, found=_has(p, {"immigration"}),
            why=f"born in {fb}" + (f"; in the U.S. by {ay}" if ay else ""),
            tells="Arrival lists after 1893 name the last residence, a relative left behind and the person joined in America; after 1906 also birthplace.",
            priority=55, searches=searchlinks.immigration(mctx))
        if fb in ("Sweden", "Norway", "Denmark", "Finland"):
            add(id="emigration", group="migration", title=f"Emigration record ({fb})", year=ay, found=_has(p, {"emigration"}),
                why=f"Nordic emigrants were recorded leaving their parish and port",
                tells="Swedish parish moving-out records and the Gothenburg emigrant registers give the home parish — the key to Swedish church books.",
                priority=55, searches=searchlinks.emigration(mctx))
        adult_arrival = (b and ay and ay - b["hi"] >= 18) or (b and ay is None)
        if male or (female and (not b or b["hi"] >= 1900)) or adult_arrival:
            add(id="naturalization", group="migration", title="Naturalization (citizenship) papers", year=None, found=_has(p, {"naturalization"}),
                why="immigrants could apply for citizenship after 5 years" + (" (married women before 1922 usually gained it through their husband)" if female else ""),
                tells="Papers after 1906 give birth date and town, arrival ship and date, spouse and children.",
                priority=45 if male else 30, searches=searchlinks.naturalization(mctx))

    # ---- military
    if male and b:
        if 1872 <= b["hi"] and b["lo"] <= 1900 and f.alive_in(pid, 1918) != "no" and _in_us(f, pid, 1917) != "no":
            ctx = {**ctx_base, "year": 1917, "place": (f.residence_near(pid, 1917) or (None,))[0]}
            add(id="draft-ww1", group="military", title="World War I draft registration (1917–18)", year=1917, found=_has(p, {"draft_ww1"}),
                why="all men born 1872–1900 living in the U.S. had to register, citizens or not",
                tells="Exact birth date, address, occupation, employer, nearest relative, physical description, signature.",
                priority=50, searches=searchlinks.draft(ctx, "ww1"))
        if 1877 <= b["hi"] and b["lo"] <= 1927 and f.alive_in(pid, 1942) != "no" and _in_us(f, pid, 1942) != "no":
            ctx = {**ctx_base, "year": 1942, "place": (f.residence_near(pid, 1942) or (None,))[0]}
            old = b["hi"] <= 1897
            add(id="draft-ww2", group="military", title="World War II draft registration" + (" (\"old man's draft\", 1942)" if old else ""), year=1942,
                found=_has(p, {"draft_ww2"}), why=("men born 1877–1897 registered in April 1942" if old else "men born 1898–1927 registered 1940–1945"),
                tells="Birth date and town, address, employer, and a person who will always know the registrant's address (often a wife or parent).",
                priority=40, searches=searchlinks.draft(ctx, "ww2"))

    # ---- other
    if dead and (not d or d["hi"] >= 1937) and b and b["hi"] >= 1865 and b["lo"] <= 1950 and _in_us(f, pid, 1940) != "no":
        ctx = {**ctx_base, "year": 1937}
        add(id="ss5", group="other", title="Social Security application (SS-5)", year=None, found=_has(p, {"social_security"}),
            why="most workers alive after 1936 applied for a Social Security number",
            tells="The application names the applicant's father and mother (mother's maiden name), birth date and birthplace — written by the applicant.",
            priority=45 if not p.parents else 30, searches=searchlinks.social_security(ctx))

    # ---- parents pathway (brick wall)
    if not p.parents:
        paths = []
        for it in items:
            if it["id"] in ("birth",) or it["id"].startswith("marriage") or it["id"] in ("death", "ss5", "obituary", "emigration") or \
                    (it["group"] == "census" and it.get("year") and by and it["year"] - by <= 15 and it["year"] >= 1850):
                paths.append({"item": it["id"], "title": it["title"], "status": it["status"], "why": _parent_why(it, bp)})
        add(id="parents", group="parents", title="Parents not in the tree", year=None, status="missing", found=[],
            why="no parents are recorded for this person", tells="These records usually name parents — work through them in this order.",
            priority=95, paths=paths)

    for it in items:
        it["group_label"] = GROUPS[it["group"]]
    order = {"missing": 0, "maybe": 1, "found": 2, "lost": 3}
    items.sort(key=lambda it: (list(GROUPS).index(it["group"]), it.get("year") or 0))
    counts = {k: sum(1 for i in items if i["status"] == k and i["id"] != "parents") for k in order}
    return {"person": f.summary(pid), "names": forms, "items": items, "counts": counts}


def _parent_why(it, bp) -> str:
    i = it["id"]
    if i == "birth":
        return "Birth and baptism records name both parents."
    if i.startswith("marriage"):
        return "Marriage records name the parents of bride and groom in many places (Massachusetts from 1841)."
    if i == "death":
        return "Death certificates usually name father and mother (and often the mother's maiden name)."
    if i == "ss5":
        return "The applicant wrote in both parents' names."
    if i == "obituary":
        return "Names brothers and sisters — whose records may name the parents."
    if i == "emigration":
        return "Gives the home parish, whose church books record the family."
    return "As a child, the person appears in the parents' household."


def opportunities(f: Family, root: str | None, limit: int = 20) -> list:
    """The most useful next steps across the tree: direct ancestors first, brick walls first."""
    if not f.people:
        return []
    direct: dict[str, int] = {}
    if root and root in f.people:
        stack = [(root, 0)]
        while stack:
            x, g = stack.pop()
            if x in direct:
                continue
            direct[x] = g
            stack.extend((pa, g + 1) for pa in f.people[x].parents)
    out = []
    for pid in f.people:
        p = f.people[pid]
        if p.living == "living":
            continue
        b = f.birth(pid)
        if b and b["lo"] > 1950:
            continue
        cl = build(f, pid)
        for it in cl["items"]:
            if it["status"] != "missing":
                continue
            score = it["priority"]
            if pid in direct:
                score += 30 - min(direct[pid], 6) * 2
            else:
                score -= 15
            if it["group"] == "census" and not it["expect"].get("place"):
                score -= 10
            out.append({"person": f.summary(pid), "item": it, "score": score, "direct": pid in direct,
                        "generation": direct.get(pid)})
    out.sort(key=lambda o: -o["score"])
    # at most 2 per person so one person doesn't fill the list
    per, res = {}, []
    for o in out:
        k = o["person"]["id"]
        if per.get(k, 0) >= 2:
            continue
        per[k] = per.get(k, 0) + 1
        res.append(o)
        if len(res) >= limit:
            break
    return res
