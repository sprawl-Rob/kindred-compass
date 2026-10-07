"""Society and member sites the user belongs to: American Ancestors (NEHGS), the NYG&B, and the
Herkimer County Historical Society.

None of these is searched automatically:
* American Ancestors' search results come from app.americanancestors.org, whose robots.txt disallows
  /SearchResults/ — so the app builds the search URL and opens it in the user's own browser, where they
  are signed in. (URL format checked 2026-10-07.)
* The NYG&B's search form posts through an "antibot" check and its terms prohibit granting access to the
  member services "through any means" and downloading significant portions — so the app links to the
  search page and gives the search terms to paste.
* The Herkimer County Historical Society's resources are a physical library (plus a password-protected
  members' page); the app lists the holdings that fit the person and prepares a research request.

The app never stores passwords for these sites.
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

from . import placenorm

NEW_ENGLAND = {"Massachusetts", "New Hampshire", "Maine", "Vermont", "Connecticut", "Rhode Island"}

AA_SEARCH = "https://www.americanancestors.org/search/database-search"
NYGB_SEARCH = "https://www.newyorkfamilyhistory.org/online-records"
HCHS = {
    "name": "Herkimer County Historical Society",
    "resources_url": "https://herkimercountyhistory.org/rescources/",
    "members_url": "https://herkimercountyhistory.org/members-only/",
    "email": "herkimerhistoryresearch@yahoo.com",
    "address": "400 N. Main St., Herkimer, NY 13350",
    "checked": "2026-10-07",
}

# Holdings listed on https://herkimercountyhistory.org/rescources/ (checked 2026-10-07)
HCHS_CENSUS = [1790, 1800, 1810, 1820, 1825, 1830, 1835, 1845, 1855, 1865, 1880]
HCHS_DIRECTORIES_HERKIMER = [1869, 1886, 1888, 1893, 1902, 1904, 1907, 1909, 1913, 1916, 1921, 1925, 1929, 1936, 1938, 1940, 1942, 1945, 1947,
                             1951, 1953, 1955, 1957, 1958, 1960, 1961, 1962, 1964, 1965, 1968, 1970, 1971, 1972, 1974, 1975, 1976, 1977, 1978,
                             1979, 1983, 1984, 1985, 1987, 1988, 1990, 1991, 1992, 1995]
HCHS_DIRECTORIES_LITTLE_FALLS = [1886, 1918, 1928, 1936, 1947, 1949, 1951, 1953, 1964, 1965, 1970, 1971, 1973, 1975, 1977, 1986, 1987, 1989, 1990,
                                 1992, 1995]


NY_COUNTIES = ["Albany", "Allegany", "Bronx", "Broome", "Cattaraugus", "Cayuga", "Chautauqua", "Chemung", "Chenango", "Clinton", "Columbia",
               "Cortland", "Delaware", "Dutchess", "Erie", "Essex", "Franklin", "Fulton", "Genesee", "Greene", "Hamilton", "Herkimer", "Jefferson",
               "Kings", "Lewis", "Livingston", "Madison", "Monroe", "Montgomery", "Nassau", "New York", "Niagara", "Oneida", "Onondaga", "Ontario",
               "Orange", "Orleans", "Oswego", "Otsego", "Putnam", "Queens", "Rensselaer", "Richmond", "Rockland", "Saratoga", "Schenectady",
               "Schoharie", "Schuyler", "Seneca", "St. Lawrence", "Steuben", "Suffolk", "Sullivan", "Tioga", "Tompkins", "Ulster", "Warren",
               "Washington", "Wayne", "Westchester", "Wyoming", "Yates"]


def ny_county(name: str | None) -> str | None:
    """Correct a New York county name as written in a tree ('Herikmer' → 'Herkimer')."""
    if not name:
        return None
    import difflib
    n = name.strip().removesuffix(" County").removesuffix(" Co.").strip()
    m = difflib.get_close_matches(n.title(), NY_COUNTIES, n=1, cutoff=0.75)
    return m[0] if m else None


def regions(f, pid) -> set:
    """States / provinces / countries where the person (or their records) are placed."""
    out = set()
    for e in f.people[pid].events:
        pl = e.place
        if pl.is_us and pl.state:
            out.add(pl.state)
        elif pl.country == "Canada" and pl.state:
            out.add(pl.state if pl.state.lower() not in ("québec", "quebec") else "Quebec")
        elif pl.country:
            out.add(pl.country)
    return out


def _place_text(place) -> str | None:
    if isinstance(place, placenorm.Place) and (place.town or place.state):
        if place.is_us:
            return ", ".join(x for x in [place.town, place.state] if x)
        return ", ".join(x for x in [place.town, place.state, place.country] if x)
    return None


def american_ancestors(ctx: dict, year_from=None, year_to=None, place=None) -> dict:
    f = ctx["forms"]
    q = {"firstname": f["given"], "lastname": ctx.get("surname") or f["surname"]}
    if year_from:
        q["fromyear"] = year_from
    if year_to:
        q["toyear"] = year_to
    pt = _place_text(place)
    if pt:
        q["location"] = pt
    q.update({"allData": "true", "searchPage": "Advanced-Search", "exactRecordType": "true"})
    return {"site": "American Ancestors", "label": "American Ancestors (your membership)", "url": AA_SEARCH + "?" + urlencode(q, quote_via=quote),
            "free": False, "login": "membership", "member": True}


def nygb(ctx: dict, county: str | None = None) -> dict:
    f = ctx["forms"]
    terms = f"{f['given']} {ctx.get('surname') or f['surname']}".strip()
    return {"site": "NYG&B", "label": "NYG&B online records (your membership)", "url": NYGB_SEARCH, "free": False, "login": "membership",
            "member": True, "copy": terms + (f" — Location: {county} County" if county else ""),
            "note": "The NYG&B search can't be pre-filled; paste the name" + (f" and choose {county} County" if county else "") + "."}


def add_member_links(f, pid, items: list, ctx_base: dict) -> None:
    """Append American Ancestors / NYG&B links to checklist items where those collections are strong."""
    reg = regions(f, pid)
    ne_ny_qc = bool(reg & (NEW_ENGLAND | {"New York", "Quebec"}))
    ny = "New York" in reg
    county = next((ny_county(e.place.county) for e in f.people[pid].events if e.place.state == "New York" and ny_county(e.place.county)), None)
    for it in items:
        if it["status"] not in ("missing", "maybe") or it["group"] in ("parents", "military") or it["id"] in ("herkimer-hs", "ss5"):
            continue
        y = it.get("year")
        e = it.get("expect") or {}
        place = None
        if isinstance(e.get("place"), str):
            place = placenorm.parse(e["place"])
        ctx = {**ctx_base, "surname": ctx_base.get("surname_at", {}).get(y) if y else None}
        if ne_ny_qc and it["group"] in ("census", "vital", "migration", "other"):
            yf, yt = (y - 2, y + 2) if y else (None, None)
            if it["id"].startswith("census") or it["id"].startswith("state-census"):
                yf = yt = y
            it.setdefault("searches", []).append(american_ancestors(ctx, yf, yt, place))
        if ny and it["group"] in ("census", "vital", "other"):
            it.setdefault("searches", []).append(nygb(ctx, county))


def herkimer_item(f, pid, ctx_base: dict) -> dict | None:
    """The Herkimer County Historical Society library, for people who lived in Herkimer County, with the holdings that fit them."""
    p = f.people[pid]
    ev = [e for e in p.events if e.place.state == "New York" and ny_county(e.place.county) == "Herkimer"
          or (e.place.state == "New York" and (e.place.town or "").lower() in ("herkimer", "little falls", "ilion", "mohawk", "frankfort", "dolgeville"))]
    if not ev:
        return None
    years = [e.year for e in ev if e.year]
    b, d = f.birth(pid), f.death(pid)
    lo = (b["lo"] if b else None) or (min(years) - 30 if years else 1790)
    hi = (d["hi"] if d else None) or (max(years) + 10 if years else 1950)
    towns = sorted({e.place.town for e in ev if e.place.town})
    holdings = []
    cen = [y for y in HCHS_CENSUS if lo <= y <= hi]
    if cen:
        holdings.append("Census copies: " + ", ".join(map(str, cen)) + " (NY state censuses 1825, 1835, 1845, 1855, 1865 included)")
    dirs = [y for y in HCHS_DIRECTORIES_HERKIMER if max(lo + 16, 1869) <= y <= hi]
    if dirs:
        holdings.append(f"Herkimer–Mohawk–Ilion–Frankfort city directories: {dirs[0]}–{dirs[-1]} ({len(dirs)} years)")
    if any(t.lower() in ("little falls", "dolgeville") for t in towns):
        lf = [y for y in HCHS_DIRECTORIES_LITTLE_FALLS if lo + 16 <= y <= hi]
        if lf:
            holdings.append(f"Little Falls & Dolgeville directories: {', '.join(map(str, lf))}")
    if lo <= 1930:
        holdings.append("Cemetery files: transcriptions of gravestones in every Herkimer County cemetery, up to 1930")
    if hi >= 1800 and lo <= 1944:
        holdings.append("Newspaper marriages & obituaries: 1800s papers, Herkimer/Ilion Citizen 1867–1921, Evening Telegram 1900–1920; "
                        "obituary index to the Evening Telegram 1923–1944")
    if lo <= 1900:
        holdings.append("Abstracts of wills: will index 1790s–1900")
    holdings.append("Family genealogies and surname files, town & village histories, gazetteers (1860, 1875), county atlases (1868, 1906), vertical files")
    f_ = ctx_base["forms"]
    summary = f.summary(pid)
    body = (f"Hello,\n\nI'm a member researching {summary['name']}"
            + (f" (born {summary['birth']}" + (f", died {summary['death']}" if summary.get("death") else "") + ")" if summary.get("birth") else "")
            + (f", who lived in {', '.join(towns)}" if towns else " in Herkimer County") + ".\n\n"
            "Could you check your surname files, cemetery files, obituary/marriage indexes, directories and will index for this person and their family?\n\nThank you,\n")
    mail = f"mailto:{HCHS['email']}?" + urlencode({"subject": f"Research request: {f_['given']} {f_['surname']}", "body": body}, quote_via=quote)
    place_label = ", ".join(towns) if towns else "Herkimer County"
    return {"id": "herkimer-hs", "group": "other", "title": "Herkimer County Historical Society library", "year": None, "status": "missing",
            "found": [], "priority": 55,
            "why": f"lived in {place_label}, NY" + (f" ({min(years)}–{max(years)})" if years else ""),
            "tells": "Holdings that fit this person: " + " · ".join(holdings) + ". Members get free research by the Society's staff "
                     f"(otherwise a $30 donation); the library is at {HCHS['address'].replace('400', '406')}.",
            "searches": [
                {"site": "Ask the Society", "label": "Email a research request (opens your mail app; free for members)", "url": mail, "free": True},
                {"site": "HCHS resources", "label": "Library holdings", "url": HCHS["resources_url"], "free": True},
                {"site": "HCHS members", "label": "Members-only page (uses the Society's members password)", "url": HCHS["members_url"], "free": False,
                 "login": "members password", "member": True},
            ]}
