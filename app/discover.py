"""Search all sources for a name — not tied to anyone already in the tree.

* links(): every source in the directory that covers the place and years, with a pre-filled search where the
  URL format is verified (American Ancestors, FamilySearch, Find a Grave, …) or the search terms to paste
  (NYG&B and others). Society/subscription sources the user belongs to are marked as theirs.
* plan_query(): the searches the app can run itself (1950 and Irish censuses, newspapers, books, …) for the
  name, its common forms and spellings, the years and the place. Runs reuse the research-run machinery, so
  every search is logged and every result is checked the same way.
* new_person_from_hit() / assign_hit(): a found record becomes a new person in the tree (optionally linked
  to a relative already there), or is attached to an existing person.
"""
from __future__ import annotations

from . import directory as d, nameequiv, names as nm, placenorm, settings_store as st, workspace as ws
from .db import new_id, now_iso, one, update
from .directory import NotFound, ValidationError
from .integrations import ADAPTERS, build_search_link
from .membersites import NYGB_SEARCH, ny_county
from .research import matching as mt


def parse_query(q: dict) -> dict:
    given = (q.get("given") or "").strip()
    surname = (q.get("surname") or "").strip()
    if not surname:
        raise ValidationError("Enter at least a surname")

    def yr(v):
        try:
            v = int(str(v).strip())
            return v if 1000 <= v <= 2100 else None
        except (TypeError, ValueError):
            return None
    yf, yt = yr(q.get("year_from")), yr(q.get("year_to"))
    if yf and yt and yf > yt:
        yf, yt = yt, yf
    place = placenorm.parse(q.get("place") or "")
    return {"given": given, "surname": surname, "year_from": yf, "year_to": yt, "place": place, "place_text": (q.get("place") or "").strip(),
            "keywords": (q.get("keywords") or "").strip()}


def _place_for_search(pl: placenorm.Place) -> str:
    if pl.is_us:
        return ", ".join(x for x in [pl.town, pl.state] if x)
    return ", ".join(x for x in [pl.town, pl.state, pl.country] if x)


def links(conn, query: dict) -> dict:
    q = parse_query(query)
    pl = q["place"]
    subs = set((st.get(conn, "research_prefs") or {}).get("subscriptions") or [])
    filt = {"year_from": q["year_from"], "year_to": q["year_to"]}
    if pl.country:
        filt["country"] = pl.country
    if pl.state:
        filt["region"] = pl.state
    if pl.county:
        filt["county"] = pl.county
    elif pl.state == "New York" and pl.town:
        c = ny_county(pl.town) if pl.town in ("Herkimer",) else None
        if c:
            filt["county"] = c
    res = d.filter_collections(conn, filt)
    values = {"given": q["given"], "surname": q["surname"], "year_from": q["year_from"], "year_to": q["year_to"],
              "place": _place_for_search(pl), "state": pl.state if pl.is_us else "", "q": " ".join(x for x in [q["given"], q["surname"], q["keywords"]] if x)}
    out = []
    for group in ("match", "partial", "unknown"):
        for c in res["groups"].get(group, []):
            if c.get("entry_kind") in ("guide", "directory"):
                continue
            link = build_search_link(c, values)
            acc = set(c.get("access_search") or [])
            mine = c.get("provider_id") in subs
            copy = None
            if not link["prefilled"]:
                copy = values["q"]
                if c.get("seed_key") == "nygb-online-records" and (pl.county or pl.state == "New York"):
                    county = ny_county(pl.county) if pl.county else None
                    copy = f"{values['q']}" + (f" — Location: {county} County" if county else "")
            out.append({"collection_id": c["id"], "name": c["name"], "provider": c.get("provider_name"), "provider_id": c.get("provider_id"), "url": link["url"],
                        "prefilled": link["prefilled"], "note": c.get("search_link_notes") or link["note"], "copy": copy,
                        "coverage": group, "coverage_why": "; ".join(x for x in [c["coverage"].get("geo_why"), c["coverage"].get("dates_why")] if x),
                        "access": sorted(acc), "mine": mine, "free": bool(acc & {"free", "free_account"}),
                        "membership": bool(set((c.get("access_search") or []) + (c.get("access_images") or []) + (c.get("access_copies") or []))
                                           & {"subscription", "library"}) or "membership" in (c.get("tags") or []),
                        "record_types": (c.get("record_types") or [])[:6], "seed_key": c.get("seed_key")})
    # yours first, then pre-filled, then by coverage
    rank = {"match": 0, "partial": 1, "unknown": 2}
    out.sort(key=lambda o: (not o["mine"], rank[o["coverage"]], not o["prefilled"], not o["free"], o["name"]))
    return {"query": {k: v for k, v in q.items() if k != "place"} | {"place": pl.as_dict()}, "links": out,
            "hidden_by_preferences": len(res.get("hidden_by_preferences") or [])}


# ------------------------------------------------------------------ searches the app runs itself

def name_forms(q: dict) -> list:
    out = [(f"{q['given']} {q['surname']}".strip(), "the name as entered")]
    if q["given"]:
        for e in [x for x in nameequiv.given_equivalents(q["given"]) if len(x) > 2 and not nameequiv.is_abbreviation(x)][:2]:
            out.append((f"{e} {q['surname']}", f"“{e}” was commonly written for {q['given']}"))
    for v in list(dict.fromkeys(nameequiv.surname_variants(q["surname"]) + nm.spelling_variants(q["surname"])))[:2]:
        out.append((f"{q['given']} {v}".strip(), f"spelling “{v}”"))
    return out


def plan_query(conn, creds, query: dict, options: dict) -> dict:
    from .research.engine import archive_status
    q = parse_query(query)
    pl = q["place"]
    statuses = {a["key"]: a for a in archive_status(creds, conn)}
    forms = name_forms(q)
    queries, skipped = [], []
    for key, a in statuses.items():
        if options.get("adapters") and key not in options["adapters"]:
            continue
        if not a["usable"]:
            skipped.append({"adapter": key, "label": a["label"], "reason": "needs your API key" if a["requires_key"] and not a["has_key"] else "turned off"})
            continue
        cls = ADAPTERS[key]
        cov = cls.coverage or {}
        if key == "census_1950":
            if not pl.is_us or not pl.state or (q["year_to"] and q["year_to"] < 1900) or (q["year_from"] and q["year_from"] > 1950):
                skipped.append({"adapter": key, "label": a["label"], "reason": "needs a U.S. state, and years that include 1950 (or no years)"})
                continue
            queries.append({"adapter": key, "label": a["label"], "query": {"text": forms[0][0], "state": pl.state, "place": pl.county or None,
                                                                         "year_from": 1950, "year_to": 1950},
                            "reason": f"1950 census pages for {pl.county + ' County, ' if pl.county else ''}{pl.state}"})
            continue
        if key == "census_ireland":
            from .integrations.census import irish_county
            county = irish_county(pl)
            if pl.country != "Ireland" and not county:
                skipped.append({"adapter": key, "label": a["label"], "reason": "the place isn't in Ireland"})
                continue
            queries.append({"adapter": key, "label": a["label"], "query": {"text": forms[0][0], "place": county, "year_from": 1901, "year_to": 1911},
                            "reason": "1901 and 1911 census of Ireland" + (f", Co. {county}" if county else "")})
            continue
        countries = cov.get("countries")
        if countries and pl.country and pl.country not in countries:
            skipped.append({"adapter": key, "label": a["label"], "reason": f"covers {', '.join(countries)}"})
            continue
        qf = max(q["year_from"], cov["from"]) if (q["year_from"] and cov.get("from")) else q["year_from"]
        qt = min(q["year_to"], cov["to"]) if (q["year_to"] and cov.get("to")) else q["year_to"]
        if qf and qt and qf > qt:
            skipped.append({"adapter": key, "label": a["label"], "reason": f"covers {cov.get('from')}–{cov.get('to')}"})
            continue
        for text, why in forms:
            queries.append({"adapter": key, "label": a["label"], "query": {"text": text + (f" {q['keywords']}" if q["keywords"] else ""), "phrase": True,
                                                                         "year_from": qf, "year_to": qt,
                                                                         "state": pl.state if pl.is_us and "United States" in (countries or []) else None},
                            "reason": why})
    by: dict = {}
    for x in queries:
        by.setdefault(x["adapter"], []).append(x)
    ordered = []
    while any(by.values()):
        for k in list(by):
            if by[k]:
                ordered.append(by[k].pop(0))
    limit = int(options.get("max_queries") or 16)
    return {"query": {k: v for k, v in q.items() if k != "place"} | {"place": pl.as_dict()}, "queries": ordered[:limit],
            "dropped": max(0, len(ordered) - limit), "skipped_archives": skipped, "names": [t for t, _ in forms]}


def profile_from_query(query: dict) -> mt.Profile:
    q = parse_query(query)
    pl = q["place"]
    places = [mt.fold(x) for x in (pl.town, pl.county, pl.state) if x]
    givens = [mt.fold(q["given"]).split()[0]] if q["given"] else []
    equivs = [mt.fold(e) for e in nameequiv.given_equivalents(q["given"])] if q["given"] else []
    surn = [mt.fold(q["surname"])]
    variants = [mt.fold(v) for v in nameequiv.surname_variants(q["surname"]) + nm.spelling_variants(q["surname"]) + nm.ocr_variants(q["surname"])]
    return mt.Profile(givens, surn, [v for v in dict.fromkeys(variants) if v and v not in surn], q["year_from"], q["year_to"], places,
                      [], None, None, None, [e for e in dict.fromkeys(equivs) if e and e not in givens], [], [], surn)


# ------------------------------------------------------------------ results → people

def assign_hit(conn, hit_id: str, person_id: str) -> dict:
    h = one(conn, "SELECT * FROM research_hits WHERE id = ?", (hit_id,))
    p = one(conn, "SELECT * FROM persons WHERE id = ?", (person_id,))
    if not h or not p:
        raise NotFound("result or person")
    if p["project_id"] != h["project_id"]:
        raise ValidationError("That person is in a different project")
    update(conn, "research_hits", hit_id, {"person_id": person_id})
    from .research.engine import save_hit
    return save_hit(conn, hit_id, auto=False, identity="probable")


def new_person_from_hit(conn, hit_id: str, data: dict) -> dict:
    """Create a person from a found record (name, sex, an approximate fact), optionally related to someone in the tree."""
    h = one(conn, "SELECT * FROM research_hits WHERE id = ?", (hit_id,))
    if not h:
        raise NotFound("result")
    given, surname = (data.get("given") or "").strip(), (data.get("surname") or "").strip()
    if not (given or surname):
        raise ValidationError("Enter the person's name")
    claims = []
    if data.get("fact_type") and (data.get("date_text") or data.get("place")):
        pl = placenorm.parse(data.get("place") or "")
        claims.append({"claim_type": data["fact_type"], "date_text": data.get("date_text") or "", "status": "working",
                       "place": {"name": data.get("place"), "country": pl.country, "region": pl.state, "county": pl.county, "municipality": pl.town}
                       if data.get("place") else {}})
    person = ws.create_person(conn, h["project_id"], {"names": [{"name_type": "birth", "given": given, "surname": surname}],
                                                      "sex": data.get("sex") or None, "living_status": data.get("living_status") or "unknown",
                                                      "claims": claims})
    rel_to, rel = data.get("related_person_id"), data.get("relationship")
    if rel_to and rel in ("parent", "child", "spouse", "sibling"):
        other = one(conn, "SELECT project_id FROM persons WHERE id = ?", (rel_to,))
        if not other or other["project_id"] != h["project_id"]:
            raise ValidationError("The related person isn't in this project")
        # rel describes the NEW person: "child of X" → claim on the new person
        ws.create_claim(conn, h["project_id"], {"person_id": person["id"], "claim_type": "relationship", "relationship_type": rel,
                                                "related_person_id": rel_to, "status": "tentative",
                                                "statement": f"Added from a search result: {h['title']}"})
    assign_hit(conn, hit_id, person["id"])
    return person
