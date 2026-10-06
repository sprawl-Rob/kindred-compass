"""Census name searches the app can run itself (verified live 2026-10-06; notes: tools/research/census_sources.md).

- 1950 U.S. census (National Archives): the JSON API behind 1950census.archives.gov. It is undocumented, so it may
  change; robots.txt asks for at most one request a second. Each result is one schedule page; the names are
  machine-read (OCR) or volunteer-corrected and often noisy. Searched by surname within a state and county.
- 1901 and 1911 census of Ireland (National Archives of Ireland): public JSON API, one row per person with age,
  relationship to head, occupation and birthplace. Reuse terms are not published, so unsaved results are
  trimmed after 30 days like other cached archive results.

FamilySearch and Ancestry census indexes cannot be searched automatically (their terms forbid it); the app
builds ready-made links to them instead (app/searchlinks.py).
"""
from __future__ import annotations

import re
from urllib.parse import urlencode

from .. import placenorm
from .base import Hit, IntegrationError, SearchAdapter, SearchQuery, SearchResult


def _split_name(text: str) -> tuple[str, str]:
    t = re.sub(r"^(mrs|mr|miss|dr)\.?\s+", "", (text or "").strip(), flags=re.IGNORECASE).replace('"', "")
    parts = t.split()
    if not parts:
        raise IntegrationError("Enter a name to search for.")
    return (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else ("", parts[0])


class US1950CensusAdapter(SearchAdapter):
    key = "census_1950"
    label = "1950 U.S. census (National Archives)"
    provider = "U.S. National Archives"
    documentation_url = "https://1950census.archives.gov/about/"
    terms_note = ("Searches the National Archives' free 1950 census name index (machine-read and volunteer-corrected names), "
                  "one request a second as its robots.txt asks. The search service is not formally documented and may change.")
    record_kind = "census page"
    max_per_minute = 30
    verified_live = "2026-10-06"
    coverage = {"countries": ["United States"], "from": 1950, "to": 1950}
    BASE = "https://1950census.archives.gov"

    def search(self, q: SearchQuery) -> SearchResult:
        given, surname = _split_name(q.text)
        st = placenorm.STATE_ABBR.get((q.state or "").lower()) if q.state else None
        if not st:
            raise IntegrationError("The 1950 census search needs a U.S. state.")
        params = {"state": st, "name": surname, "page": 1, "size": 25}
        county = (q.place or "").strip()
        if county:
            params["county"] = county
        data = self._get_json(self.BASE + "/api/search", params)
        results = list(data.get("results") or [])
        # Common surnames fill several pages; read up to four (one request a second).
        pages = min(4, -(-(data.get("total") or 0) // 25))
        for pg in range(2, pages + 1):
            results += self._get_json(self.BASE + "/api/search", {**params, "page": pg}).get("results") or []
        hits = []
        for r in results:
            hl = (r.get("highlight") or {})
            matched = list(dict.fromkeys((hl.get("transcribe.name") or []) + (hl.get("names.name") or [])))
            src = [x for x in (r.get("transcribe") or []) if x.get("name")] or [x for x in (r.get("names") or []) if x.get("name")]
            rows = sorted(({**x, "name": re.sub(r"(?<=[a-z])(?=[A-Z])", " ", x["name"])} for x in src), key=lambda x: (x.get("row") or 0))
            for name in matched[:4]:
                name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)   # OCR glue: "HildaC." → "Hilda C."
                if not _given_fits(name, surname, given):
                    continue
                household = _household_1950(rows, name, surname)
                place = f"{r.get('county')}, {r.get('state')}"
                hits.append(Hit(item_id=f"{r.get('scheduleId')}:{name}", title=f"1950 census: {_reorder(name, surname)} (ED {r.get('ed')})",
                                url=self.BASE + "/search/?" + urlencode({"county": r.get("county") or "", "name": surname, "page": 1, "size": 25, "state": st}),
                                date_text="1950-04-01", snippet=household, place_text=f"{place} (ED {r.get('ed')})", collection="1950 U.S. census",
                                record_kind="census page",
                                extra={"ed": r.get("ed"), "schedule_id": r.get("scheduleId"), "image": r.get("image"), "match_place": r.get("state"),
                                       "note": "Names are machine-read from the handwritten page; open the image to check."}))
        return SearchResult(hits, data.get("total"), self.BASE + "/search/?" + urlencode({k: v for k, v in params.items() if k in ("state", "county", "name")}))


def _plan_1950(f, pid) -> tuple[list, str | None]:
    if f.alive_in(pid, 1950) == "no":
        return [], "not alive in 1950"
    b = f.birth(pid)
    if b and b["lo"] > 1950:
        return [], "born after 1950"
    near = f.residence_near(pid, 1950)
    if not near or not near[0].is_us or not near[0].state:
        return [], "no U.S. residence recorded near 1950"
    pl = near[0]
    p = f.people[pid]
    given = (p.givens[0].split()[0] if p.givens else "").replace('"', "")
    surnames = []
    if (p.sex or "").upper().startswith("F"):
        surnames += [f.people[s].surnames[0] for s in p.spouses if f.people[s].surnames] + p.married_surnames
    surnames += p.surnames
    out = []
    for sn in list(dict.fromkeys(surnames))[:2]:
        out.append({"text": f"{given} {sn}".strip(), "state": pl.state, "place": pl.county or pl.town, "years": (1950, 1950),
                    "why": f"recorded in {pl.short()} in {near[1]} — searching the 1950 census pages for {pl.county + ' County' if pl.county else pl.short()}"})
    return out, None


def _plan_ireland(f, pid) -> tuple[list, str | None]:
    p = f.people[pid]
    irish = [e.place for e in p.events if e.place.country == "Ireland"]
    bp = f.birth_place(pid)
    via = ""
    if not irish and not (bp and bp.country == "Ireland"):
        # a child born in Ireland means the parent lived there
        kids = [f.birth_place(c) for c in p.children]
        irish = [k for k in kids if k and k.country == "Ireland"]
        if not irish:
            return [], "no Irish place recorded for this person or their children"
        via = " (a child was born there)"
    arr = f.arrival_year(pid)
    years = []
    for y in (1901, 1911):
        if f.alive_in(pid, y) == "no":
            continue
        if arr and arr["year"] <= y and not arr.get("upper_bound"):
            continue   # already emigrated
        if arr and arr.get("upper_bound") and arr["year"] <= y:
            continue
        years.append(y)
    if not years:
        return [], "not in Ireland in 1901 or 1911 (emigrated earlier or not alive)"
    county = irish_county(bp) or next((irish_county(x) for x in irish if irish_county(x)), None)
    given = (p.givens[0].split()[0] if p.givens else "").replace('"', "")
    sn = f.search_surname(pid)
    if not sn:
        return [], "no surname recorded"
    return [{"text": f"{given} {sn}".strip(), "place": county, "years": (min(years), max(years)),
             "why": f"in Ireland{via}{' — Co. ' + county if county else ''}, and not known to have left before {max(years)}"}], None


def _household_1950(rows: list, name: str, surname: str) -> str:
    """The matched line and the lines after it until the next surname — on census pages a blank surname means 'same as above'."""
    idx = next((i for i, x in enumerate(rows) if x["name"] == name), None)
    if idx is None:
        return name
    out = [_reorder(name, surname)]
    for x in rows[idx + 1: idx + 12]:
        n = x["name"].strip()
        w = n.split()
        if not w:
            continue
        continuation = len(w) == 1 or (len(w) == 2 and re.match(r"^[A-Za-z]\.?$", w[1]))
        if not continuation:
            break   # a line with its own surname starts the next household (or a boarder)
        out.append(f"{n} {surname} (listed below, surname not repeated)")
    return "Same page: " + "; ".join(out)


def _given_fits(row_name: str, surname: str, given: str) -> bool:
    """Keep only lines whose given name could be the person's (same name, a known equivalent, or the same initial)."""
    if not given:
        return True
    from ..nameequiv import given_equivalents, fold
    forms = {fold(given.split()[0])} | {fold(x) for x in given_equivalents(given)}
    toks = [fold(t).strip(".") for t in row_name.split() if fold(t).strip(".") and fold(t) != fold(surname)]
    for t in toks:
        if t in forms or (len(t) == 1 and t == fold(given)[0]) or any(len(t) >= 4 and (f.startswith(t) or t.startswith(f)) for f in forms if len(f) >= 4):
            return True
    return False


def _reorder(name: str, surname: str) -> str:
    parts = name.split()
    if parts and parts[0].lower() == surname.lower():
        return " ".join(parts[1:] + parts[:1])
    return name


IRISH_COUNTIES = ["Antrim", "Armagh", "Carlow", "Cavan", "Clare", "Cork", "Donegal", "Down", "Dublin", "Fermanagh", "Galway", "Kerry", "Kildare",
                  "Kilkenny", "Laois", "Queen's Co.", "King's Co.", "Leitrim", "Limerick", "Londonderry", "Longford", "Louth", "Mayo", "Meath", "Monaghan",
                  "Offaly", "Roscommon", "Sligo", "Tipperary", "Tyrone", "Waterford", "Westmeath", "Wexford", "Wicklow"]


def irish_county(place: placenorm.Place | None) -> str | None:
    if not place:
        return None
    for v in (place.state, place.county, place.town, place.raw):
        if not v:
            continue
        for c in IRISH_COUNTIES:
            if re.search(rf"\b{re.escape(c)}\b", v, re.IGNORECASE):
                return c
    return None


class IrishCensusAdapter(SearchAdapter):
    key = "census_ireland"
    label = "Census of Ireland 1901 & 1911 (National Archives of Ireland)"
    provider = "National Archives of Ireland"
    documentation_url = "https://nationalarchives.ie/collections/search-the-census/"
    terms_note = ("Searches the free 1901 and 1911 census of Ireland (one row per person: age, relationship, occupation, birthplace), "
                  "about one request a second. Reuse terms are not published; unsaved results are trimmed after 30 days.")
    record_kind = "census return"
    max_per_minute = 30
    supports_text = True
    cache_days = 30
    verified_live = "2026-10-06"
    coverage = {"countries": ["Ireland"], "from": 1901, "to": 1911}
    API = "https://api-census.nationalarchives.ie/census/query"

    def search(self, q: SearchQuery) -> SearchResult:
        given, surname = _split_name(q.text)
        years = [y for y in (1901, 1911) if (q.year_from is None or q.year_from <= y) and (q.year_to is None or y <= q.year_to)] or [1901, 1911]
        hits, total = [], 0
        for y in years:
            params = {"surname": surname, "census_year": y, "limit": max(1, min(50, q.page_size))}
            if given:
                params["firstname"] = given.split()[0]
            if q.place:
                params["county"] = q.place
            data = self._get_json(self.API, params)
            res = data.get("results") or []
            total += (data.get("meta") or {}).get("count") or len(res)
            for r in res:
                hits.append(self._hit(r))
        return SearchResult(hits, total, "https://nationalarchives.ie/collections/search-the-census/search-results/#" +
                            urlencode({"surname": surname, **({"firstname": given.split()[0]} if given else {}), **({"county": q.place} if q.place else {})}))

    def _hit(self, r: dict) -> Hit:
        name = f"{r.get('firstname') or ''} {r.get('surname') or ''}".strip()
        where = ", ".join(x for x in [r.get("townland"), r.get("ded"), f"Co. {r['county']}" if r.get("county") else None] if x)
        bits = [f"{name}, aged {r['age']}" if r.get("age") is not None else name, r.get("relation_to_head_updated") or r.get("relation_to_head"),
                r.get("occupation_updated") or r.get("occupation"), r.get("marriage_status"), f"born {r['birthplace']}" if r.get("birthplace") else None,
                r.get("religion_updated") or r.get("religion"),
                f"married {r['marriage_years']} years" if r.get("marriage_years") else None,
                f"{r['children_born']} children born, {r['children_living']} living" if r.get("children_born") else None]
        return Hit(item_id=str(r.get("id")), title=f"{r.get('census_year')} census of Ireland: {name} — {where}",
                   url=f"https://nationalarchives.ie/collections/search-the-census/census-record/#id={r.get('id')}&c20_year={r.get('census_year')}",
                   date_text=f"{r.get('census_year')}-03-31", snippet=". ".join(str(b) for b in bits if b) + f". House {r.get('house_number') or '?'}, {where}.",
                   place_text=f"{where}, Ireland", collection=f"{r.get('census_year')} census of Ireland", record_kind="census return",
                   extra={"household": r.get("image_group"), "age": r.get("age"), "sex": r.get("sex")})

    def fetch_text(self, hit: Hit) -> str | None:
        """The whole household on the same census form (everyone, whatever their surname)."""
        g = hit.extra.get("household")
        if not g:
            return None
        data = self._get_json(self.API, {"census_year": (hit.date_text or "")[:4], "image_group": g, "limit": 40})
        members = [self._hit(r).snippet for r in data.get("results") or [] if str(r.get("image_group")) == str(g)]
        return ("Household on the same census form: " + " | ".join(members)) if members else None


# How the research planner targets each census (who should be in it, where, and under which names).
US1950CensusAdapter.plan_for = staticmethod(_plan_1950)
IrishCensusAdapter.plan_for = staticmethod(_plan_ireland)
