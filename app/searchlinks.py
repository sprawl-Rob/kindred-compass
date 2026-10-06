"""Ready-made searches for a specific record, on the sites that hold it.

The app cannot search Ancestry or FamilySearch itself (they need a login and offer no public
search API), so it builds the best search for you: the right collection, name, birth-year range
and place, plus the name variants to try next. Links open the site in your browser; nothing is
sent anywhere by the app.

URL formats and collection IDs are listed in COLLECTIONS below with the date they were checked.
"""
from __future__ import annotations

from urllib.parse import urlencode, quote

from . import placenorm

# FamilySearch collection IDs and Ancestry database IDs ("dbid").
# fs / anc = None means: no verified ID — the link falls back to an all-collections search.
COLLECTIONS: dict[str, dict] = {
    "census-1790": {"fs": None, "anc": "5058"},
    "census-1800": {"fs": None, "anc": "7590"},
    "census-1810": {"fs": None, "anc": "7613"},
    "census-1820": {"fs": None, "anc": "7734"},
    "census-1830": {"fs": None, "anc": "8058"},
    "census-1840": {"fs": None, "anc": "8057"},
    "census-1850": {"fs": "1401638", "anc": "8054"},
    "census-1860": {"fs": "1473181", "anc": "7667"},
    "census-1870": {"fs": "1438024", "anc": "7163"},
    "census-1880": {"fs": "1417683", "anc": "6742"},
    "census-1890": {"fs": "1610551", "anc": "5445"},
    "census-1900": {"fs": "1325221", "anc": "7602"},
    "census-1910": {"fs": "1727033", "anc": "7884"},
    "census-1920": {"fs": "1488411", "anc": "6061"},
    "census-1930": {"fs": "1810731", "anc": "6224"},
    "census-1940": {"fs": "2000219", "anc": "2442"},
    "census-1950": {"fs": "4464515", "anc": "62308"},
    "state-Massachusetts-1855": {"fs": "1459985", "anc": "4472"},
    "state-Massachusetts-1865": {"fs": "1410399", "anc": "9203"},
    "draft-ww1": {"fs": "1968530", "anc": "6482"},
    "draft-ww2-old": {"fs": "1861144", "anc": "1002"},
    "draft-ww2": {"fs": None, "anc": "2238"},
    "ss5": {"fs": None, "anc": "60901"},
    "ssdi": {"fs": "1202535", "anc": None},
    "ma-births": {"fs": "2400643", "anc": "2495"},
    "ma-marriages": {"fs": "1469062", "anc": "2511"},
    "ma-deaths": {"fs": "1463156", "anc": "2101"},
    "ma-naturalization": {"fs": "1834334", "anc": "2361"},
    "ma-passengers": {"fs": "1923995", "anc": "8745"},
    "ny-passengers": {"fs": "1368704", "anc": "7488"},
    "sweden-emigration": {"fs": "3288446", "anc": "1189"},
    "sweden-baptisms": {"fs": "1520594", "anc": "2225"},
    "ireland-census-1901": {"fs": "1626180", "anc": "70667"},
    "ireland-census-1911": {"fs": "2854327", "anc": "70564"},
    "ireland-civil": {"fs": "1408347", "anc": None},
    "ireland-catholic": {"fs": "2820100", "anc": "61039"},
}
# Checked 2026-10-06: FamilySearch IDs against its public collections metadata, Ancestry dbids against page titles.
# (FamilySearch 1790–1840 census IDs were not re-checked, so those links search all collections.)
VERIFIED_ON = "2026-10-06"


def _fs(ctx: dict, collection: str | None, *, given=None, surname=None, year_from=None, year_to=None, place=None,
        residence_year=None, event_place=None, extra: dict | None = None) -> str:
    f = ctx["forms"]
    q = {"q.givenName": given if given is not None else f["given"], "q.surname": surname if surname is not None else (ctx.get("surname") or f["surname"])}
    b = ctx.get("birth")
    if b:
        q["q.birthLikeDate.from"] = b["lo"] - 2
        q["q.birthLikeDate.to"] = b["hi"] + 2
    bp = ctx.get("birth_place")
    if bp and (bp.state or bp.country):
        q["q.birthLikePlace"] = bp.state if bp.is_us else bp.country
    if place:
        q["q.residencePlace"] = place.long() if isinstance(place, placenorm.Place) else place
        if residence_year:
            q["q.residenceDate.from"] = residence_year
            q["q.residenceDate.to"] = residence_year
    if extra:
        q.update(extra)
    if collection:
        q["f.collectionId"] = collection
    return "https://www.familysearch.org/search/record/results?" + urlencode({k: v for k, v in q.items() if v not in (None, "")})


def _anc_place(place) -> str:
    if isinstance(place, placenorm.Place):
        parts = [place.town, place.county, place.state, "usa" if place.is_us else place.country]
        return "-".join(x.lower().replace(" ", "+") for x in parts if x)
    return (place or "").lower().replace(", ", "-").replace(" ", "+")


def _anc(ctx: dict, dbid: str | None, *, given=None, surname=None, place=None, year=None, event="residence") -> str:
    """Ancestry search URL, e.g. /search/collections/7884/?name=Nils_Lindqvist&birth=1880_sweden&birth_x=5-0-0&residence=1910_fitchburg-worcester-massachusetts-usa"""
    f = ctx["forms"]
    g = (given if given is not None else f["given"]).replace('"', "").replace(" ", "+")
    s = (surname if surname is not None else (ctx.get("surname") or f["surname"])).replace(" ", "+")
    q = {"name": f"{g}_{s}"}
    b = ctx.get("birth")
    bp = ctx.get("birth_place")
    if b:
        q["birth"] = str((b["lo"] + b["hi"]) // 2)
        spread = (b["hi"] - b["lo"]) // 2 + 1
        q["birth_x"] = f"{next(x for x in (1, 2, 5, 10, 10**9) if x >= spread) if spread <= 10 else 10}-0-0"
    if bp and (bp.state or bp.country):
        q["birth"] = q.get("birth", "") + "_" + _anc_place(placenorm.Place(raw="", state=bp.state if bp.is_us else None, country=bp.country))
    if place and isinstance(place, placenorm.Place) and (place.town or place.state):
        q[event] = (str(year) if year else "") + "_" + _anc_place(place)
    base = f"https://www.ancestry.com/search/collections/{dbid}/" if dbid else "https://www.ancestry.com/search/"
    return base + "?" + urlencode(q, safe="_+-")


def _variants_note(ctx) -> str:
    f = ctx["forms"]
    parts = []
    if f["given_variants"]:
        parts.append("given name also as " + ", ".join(f["given_variants"][:6]))
    if f["surname_variants"]:
        parts.append("surname also as " + ", ".join(f["surname_variants"][:6]))
    return "; ".join(parts)


def _pair(ctx, key, title, *, place=None, year=None, event="residence", fs_extra=None) -> list:
    c = COLLECTIONS.get(key, {})
    out = [
        {"site": "FamilySearch", "label": f"FamilySearch: {title}", "url": _fs(ctx, c.get("fs"), place=place, residence_year=year if event == "residence" else None, extra=fs_extra),
         "free": True, "login": "free account", "collection": bool(c.get("fs"))},
        {"site": "Ancestry", "label": f"Ancestry: {title}", "url": _anc(ctx, c.get("anc"), place=place, year=year, event=event),
         "free": False, "login": "subscription", "collection": bool(c.get("anc"))},
    ]
    return out


def census(ctx) -> list:
    y = ctx["year"]
    links = _pair(ctx, f"census-{y}", f"{y} census", place=ctx.get("place"), year=y)
    # Variant searches: the most common reasons a census entry is missed
    f = ctx["forms"]
    alts = []
    if f["surname_variants"]:
        alts.append({"label": f"Try surname “{f['surname_variants'][0]}”", "url": _fs(ctx, COLLECTIONS.get(f'census-{y}', {}).get('fs'), surname=f["surname_variants"][0], place=ctx.get("place"), residence_year=y), "site": "FamilySearch"})
    if f["given_variants"]:
        alts.append({"label": f"Try given name “{f['given_variants'][0]}”", "url": _fs(ctx, COLLECTIONS.get(f'census-{y}', {}).get('fs'), given=f["given_variants"][0], place=ctx.get("place"), residence_year=y), "site": "FamilySearch"})
    alts.append({"label": "Surname only, in this place", "url": _fs(ctx, COLLECTIONS.get(f'census-{y}', {}).get('fs'), given="", place=ctx.get("place"), residence_year=y), "site": "FamilySearch"})
    for a in alts:
        a["alt"] = True
    return links + alts


def auto_census(ctx):
    """Censuses the app can search itself."""
    if ctx.get("year") == 1950:
        return {"adapters": ["census_1950"], "label": "Search the 1950 census now (free)"}
    return None


def irish_census(ctx) -> list:
    y = ctx["year"]
    f = ctx["forms"]
    c = COLLECTIONS[f"ireland-census-{y}"]
    nai = "https://nationalarchives.ie/collections/search-the-census/search-results/#" + urlencode(
        {"surname": f["surname"], "firstname": f["given"], "census_year": y, **({"county": ctx["county"]} if ctx.get("county") else {})})
    return [{"site": "National Archives of Ireland", "label": f"{y} census of Ireland (free)", "url": nai, "free": True},
            {"site": "FamilySearch", "label": f"FamilySearch: Ireland census {y}", "url": _fs(ctx, c["fs"]), "free": True, "login": "free account"},
            {"site": "Ancestry", "label": f"Ancestry: Ireland census {y}", "url": _anc(ctx, c["anc"]), "free": False}]


def state_census(ctx) -> list:
    return _pair(ctx, f"state-{ctx['state']}-{ctx['year']}", f"{ctx['year']} {ctx['state']} census", place=ctx.get("place"), year=ctx["year"])


def vital(ctx) -> list:
    ev = ctx["event"]
    place = ctx.get("place")
    st = place.state if place and place.is_us else None
    key = {"birth": "ma-births", "marriage": "ma-marriages", "death": "ma-deaths"}[ev] if st == "Massachusetts" else None
    title = f"{st + ' ' if key else ''}{ev} records"
    y = ctx.get("year")
    extra = {}
    if ev == "marriage" and y:
        extra = {"q.marriageLikeDate.from": y - 2, "q.marriageLikeDate.to": y + 2}
        sp = ctx.get("spouse")
        if sp:
            extra["q.spouseGivenName"] = (sp.givens[0] if sp.givens else "")
            extra["q.spouseSurname"] = (sp.surnames[0] if sp.surnames else "")
    if ev == "death" and y:
        extra = {"q.deathLikeDate.from": y - 1, "q.deathLikeDate.to": y + 1}
    links = [{"site": "FamilySearch", "label": f"FamilySearch: {title}", "url": _fs(ctx, COLLECTIONS.get(key, {}).get("fs") if key else None, extra=extra),
              "free": True, "login": "free account"}]
    links.append({"site": "Ancestry", "label": f"Ancestry: {title}", "url": _anc(ctx, COLLECTIONS.get(key, {}).get("anc") if key else None, place=place, year=y, event=ev),
                  "free": False, "login": "subscription"})
    bp = ctx.get("birth_place")
    if ev == "birth" and bp and bp.country == "Sweden":
        links[0] = {"site": "FamilySearch", "label": "FamilySearch: Sweden baptisms 1611–1920", "url": _fs(ctx, COLLECTIONS["sweden-baptisms"]["fs"]), "free": True, "login": "free account"}
        links.append({"site": "Riksarkivet", "label": "Riksarkivet (Swedish National Archives): church books", "url": "https://sok.riksarkivet.se/kyrkoarkiv", "free": True, "login": None})
    if ev == "birth" and bp and bp.country == "Ireland":
        links[0] = {"site": "FamilySearch", "label": "FamilySearch: Ireland Catholic parish registers", "url": _fs(ctx, COLLECTIONS["ireland-catholic"]["fs"]), "free": True, "login": "free account"}
        links.append({"site": "IrishGenealogy.ie", "label": "IrishGenealogy.ie: civil births (from 1864) and church records",
                      "url": "https://civilrecords.irishgenealogy.ie/churchrecords/civil-search.jsp?" + urlencode({"firstname": ctx["forms"]["given"], "surname": ctx["forms"]["surname"], "type": "B"}),
                      "free": True, "login": None})
    return links


def obituary(ctx) -> list:
    f = ctx["forms"]
    y = ctx.get("year")
    q = f'"{f["given"]} {f["surname"]}"'
    links = []
    if y and y <= 1963:
        links.append({"site": "Library of Congress", "label": "Chronicling America (free newspapers to 1963)",
                      "url": "https://www.loc.gov/collections/chronicling-america/?" + urlencode({"q": f"{f['given']} {f['surname']}", "dates": f"{y}/{y + 1}"}), "free": True})
    links.append({"site": "Newspapers.com", "label": "Newspapers.com", "url": "https://www.newspapers.com/search/?" + urlencode({"query": q, "dr_year": f"{y}-{y + 1}" if y else ""}),
                  "free": False, "login": "subscription"})
    links.append({"site": "GenealogyBank", "label": "GenealogyBank obituaries", "url": "https://www.genealogybank.com/explore/obituaries/all?" + urlencode({"fname": f["given"], "lname": f["surname"]}), "free": False})
    return links


def auto_newspaper(ctx):
    y = ctx.get("year")
    place = ctx.get("place")
    if y and y <= 1963 and (not place or place.is_us):
        return {"adapters": ["loc_chronicling_america"], "label": "Search free newspapers now"}
    return None


def burial(ctx) -> list:
    f = ctx["forms"]
    b, d = ctx.get("birth"), ctx.get("death")
    q = {"firstname": f["given"], "lastname": f["surname"]}
    if b:
        q.update({"birthyear": (b["lo"] + b["hi"]) // 2, "birthyearfilter": "5"})
    if d:
        q.update({"deathyear": (d["lo"] + d["hi"]) // 2, "deathyearfilter": "5"})
    return [{"site": "Find a Grave", "label": "Find a Grave", "url": "https://www.findagrave.com/memorial/search?" + urlencode(q), "free": True},
            {"site": "BillionGraves", "label": "BillionGraves", "url": "https://billiongraves.com/search/results?" + urlencode({"given_names": f["given"], "family_names": f["surname"]}), "free": True}]


def immigration(ctx) -> list:
    y = ctx.get("year")
    ma = ctx.get("us_state") == "Massachusetts"
    key = "ma-passengers" if ma else "ny-passengers"
    label = "Boston passenger lists 1891–1943" if ma else "New York passenger lists (Ellis Island) 1892–1925"
    anc_q = {"arrival": f"{y}_usa", "arrival_x": "5-0-0"} if y else {}
    return [{"site": "FamilySearch", "label": f"FamilySearch: {label}", "url": _fs(ctx, COLLECTIONS[key]["fs"]), "free": True, "login": "free account"},
            {"site": "Ancestry", "label": "Ancestry: arriving passenger lists", "url": _anc(ctx, COLLECTIONS[key]["anc"]) + ("&" + urlencode(anc_q, safe="_-") if anc_q else ""), "free": False},
            {"site": "Statue of Liberty – Ellis Island Foundation", "label": "Ellis Island passenger search (1820–1957, New York)", "url": "https://heritage.statueofliberty.org/", "free": True, "login": "free account"}]


def emigration(ctx) -> list:
    return [{"site": "Ancestry", "label": "Ancestry: Swedish emigration records 1783–1951", "url": _anc(ctx, COLLECTIONS["sweden-emigration"]["anc"]), "free": False},
            {"site": "FamilySearch", "label": "FamilySearch: Swedish mission emigration records", "url": _fs(ctx, COLLECTIONS["sweden-emigration"]["fs"]), "free": True, "login": "free account"},
            {"site": "Riksarkivet", "label": "Riksarkivet: Swedish emigrants and church books", "url": "https://sok.riksarkivet.se/", "free": True}]


def naturalization(ctx) -> list:
    if ctx.get("us_state") == "Massachusetts":
        c = COLLECTIONS["ma-naturalization"]
        return [{"site": "FamilySearch", "label": "FamilySearch: Massachusetts naturalization index 1906–1966", "url": _fs(ctx, c["fs"]), "free": True, "login": "free account"},
                {"site": "Ancestry", "label": "Ancestry: Massachusetts naturalization records 1798–1950", "url": _anc(ctx, c["anc"]), "free": False}]
    return [{"site": "FamilySearch", "label": "FamilySearch: all records (naturalization)", "url": _fs(ctx, None), "free": True, "login": "free account"},
            {"site": "Ancestry", "label": "Ancestry: all records", "url": _anc(ctx, None), "free": False}]


def draft(ctx, which) -> list:
    if which == "ww1":
        return _pair(ctx, "draft-ww1", "WWI draft cards", place=ctx.get("place"), year=1917)
    b = ctx.get("birth")
    key = "draft-ww2-old" if b and b["hi"] <= 1897 else "draft-ww2"
    return _pair(ctx, key, "WWII draft cards", place=ctx.get("place"), year=1942)


def social_security(ctx) -> list:
    return [{"site": "Ancestry", "label": "Ancestry: Social Security Applications and Claims Index", "url": _anc(ctx, COLLECTIONS["ss5"]["anc"]), "free": False},
            {"site": "FamilySearch", "label": "FamilySearch: Social Security Death Index", "url": _fs(ctx, COLLECTIONS["ssdi"]["fs"]), "free": True},
            {"site": "SSA", "label": "Order the original SS-5 from the Social Security Administration (FOIA)", "url": "https://www.ssa.gov/foia/request.html", "free": False}]


def birth_hint(bp, year) -> str:
    if bp and bp.country == "Sweden":
        return "Swedish parish birth books (födelseböcker) name both parents and the farm; household examination rolls (husförhörslängder) then follow the family year by year."
    if bp and bp.country == "Ireland":
        return "Irish civil birth registration began in 1864 (both parents, mother's maiden name, townland). Before that, Catholic parish baptisms name parents and sponsors."
    if bp and bp.country == "Germany":
        return "German church baptisms (Kirchenbücher) name both parents and godparents; civil registers (Standesamt) start 1874–1876."
    if bp and bp.state == "Massachusetts":
        return "Massachusetts recorded births statewide from 1841 (town records earlier): parents' names and birthplaces, father's occupation."
    return "Birth and baptism records name the parents. U.S. statewide birth registration began between about 1840 and 1920 depending on the state; church baptisms fill the gap."


def marriage_hint(place, year) -> str:
    if place and place.state == "Massachusetts":
        return "Massachusetts marriage records (from 1841) give ages, birthplaces, and both sets of parents' names — one of the best ways to find the next generation."
    return "Marriage records give ages and residences; many name the parents of the bride and groom, and witnesses who were often relatives."


def death_hint(place, year) -> str:
    if place and place.state == "Massachusetts":
        return "Massachusetts death records (from 1841) give age, birthplace, and parents' names and birthplaces."
    return "Death certificates usually give birth date and place, parents' names, spouse, and burial place; the informant is named (and may have guessed)."
