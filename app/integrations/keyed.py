"""Archive integrations that need a free API key supplied by the user.

Request shapes follow each provider's official documentation (checked 2026-10-05;
notes in tools/research/search_apis_keyed.md). They were NOT tested with a real key
during development — Settings → Archives shows them as "not yet tested live" until
the user adds a key and runs the built-in connection test.
"""
from __future__ import annotations

import html as htmllib
import re

from .base import Hit, IntegrationError, SearchAdapter, SearchQuery, SearchResult


def _first(v):
    if isinstance(v, list):
        return str(v[0]) if v else None
    if isinstance(v, dict):
        return None
    return str(v) if v is not None else None


def _strip_tags(s: str | None) -> str | None:
    if not s:
        return s
    return htmllib.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _q(q: SearchQuery) -> str:
    t = (q.text or "").strip()
    if not t:
        raise IntegrationError("Enter words to search for.")
    if q.phrase and " " in t and not t.startswith('"'):
        t = f'"{t}"'
    return t[:300]


class DPLAAdapter(SearchAdapter):
    key = "dpla"
    label = "Digital Public Library of America (API)"
    provider = "Digital Public Library of America"
    documentation_url = "https://pro.dp.la/developers/api-codex"
    terms_note = "Searches DPLA's aggregated metadata (photos, books, manuscripts from U.S. institutions); items live at the contributing institution. Metadata is CC0."
    record_kind = "catalog record"
    requires_key = True
    key_signup = "free and instant: request one by email at https://pro.dp.la/developers/policies (the key arrives by email)."
    max_per_minute = 30
    collection_seed_keys = ("dpla",)
    coverage = {"countries": ["United States"]}
    ENDPOINT = "https://api.dp.la/v2/items"

    def search(self, q: SearchQuery) -> SearchResult:
        self.check_key()
        params = {"q": _q(q), "page": max(1, q.page), "page_size": max(1, min(100, q.page_size)), "api_key": self.api_key}
        if q.year_from:
            params["sourceResource.date.after"] = str(q.year_from)
        if q.year_to:
            params["sourceResource.date.before"] = str(q.year_to)
        if q.state:
            params["sourceResource.spatial.state"] = q.state
        data = self._get_json(self.ENDPOINT, params)
        hits = []
        for d in data.get("docs") or []:
            sr = d.get("sourceResource") or {}
            date = sr.get("date")
            date_text = (date[0] if isinstance(date, list) and date else date or {}).get("displayDate") if isinstance(date, (dict, list)) else None
            places = [p.get("name") for p in (sr.get("spatial") or []) if isinstance(p, dict) and p.get("name")]
            hits.append(Hit(item_id=str(d.get("id")), title=_first(sr.get("title")) or "Untitled item", url=d.get("isShownAt") or f"https://dp.la/item/{d.get('id')}",
                            date_text=date_text, snippet=(_first(sr.get("description")) or "")[:600] or None, place_text="; ".join(places[:3]) or None,
                            collection=_first((d.get("dataProvider") or {}).get("name") if isinstance(d.get("dataProvider"), dict) else d.get("dataProvider")),
                            record_kind=self.record_kind))
        return SearchResult(hits, data.get("count"), f"https://dp.la/search?q={params['q']}")


class NARACatalogAdapter(SearchAdapter):
    key = "nara_catalog"
    label = "National Archives Catalog (API v2)"
    provider = "U.S. National Archives"
    documentation_url = "https://catalog.archives.gov/api/v2/api-docs/"
    terms_note = ("Searches the National Archives Catalog with your key (10,000 queries a month per key). NARA's terms forbid scraping or "
                  "downloading the whole catalog; this app only runs user-initiated searches.")
    record_kind = "archival record"
    requires_key = True
    key_signup = "email Catalog_API@nara.gov with your name and the email address for the key (free; a person reviews it)."
    max_per_minute = 20
    supports_text = True
    collection_seed_keys = ("nara-genealogy",)
    coverage = {"countries": ["United States"]}
    ENDPOINT = "https://catalog.archives.gov/api/v2/records/search"

    def _api(self, url, params):
        try:
            data = self._get_json(url, params, headers={"x-api-key": self.api_key or ""})
        except IntegrationError as e:
            if e.code == "bad_response":
                # NARA answers a missing/invalid key (or exhausted quota) with its HTML website and status 200.
                raise IntegrationError("The National Archives did not accept the API key (or the monthly quota is used up). Check the key in Settings → Archives.",
                                       code="auth")
            raise
        return data

    def search(self, q: SearchQuery) -> SearchResult:
        self.check_key()
        params = {"q": _q(q), "page": max(1, q.page), "limit": max(1, min(100, q.page_size)), "availableOnline": "true", "includeExtractedText": "true"}
        if q.year_from:
            params["startDate"] = str(q.year_from)
        if q.year_to:
            params["endDate"] = str(q.year_to)
        if q.state:
            params["geographicReference"] = q.state
        data = self._api(self.ENDPOINT, params)
        body = data.get("body") or {}
        hh = (body.get("hits") or {})
        hits = []
        for h in hh.get("hits") or []:
            rec = ((h.get("_source") or {}).get("record")) or {}
            na = rec.get("naId")
            dates = [d.get("logicalDate") for d in rec.get("productionDates") or [] if isinstance(d, dict)]
            text = " ".join(o.get("extractedText") or "" for o in rec.get("digitalObjects") or [] if isinstance(o, dict))[:20000]
            hits.append(Hit(item_id=str(na), title=rec.get("title") or "Untitled record", url=f"https://catalog.archives.gov/id/{na}",
                            date_text=(dates[0] or "")[:10] if dates else None, snippet=(rec.get("scopeAndContentNote") or "")[:600] or None,
                            collection=((rec.get("ancestors") or [{}])[0] or {}).get("title") if rec.get("ancestors") else None,
                            record_kind=self.record_kind, text_ref=str(na), extra={"text": text} if text else {}))
        total = (hh.get("total") or {}).get("value") if isinstance(hh.get("total"), dict) else hh.get("total")
        return SearchResult(hits, total, f"https://catalog.archives.gov/search?q={params['q']}")

    def fetch_text(self, hit: Hit) -> str | None:
        return (hit.extra or {}).get("text") or None


class TroveAdapter(SearchAdapter):
    key = "trove"
    label = "Trove newspapers (API v3)"
    provider = "National Library of Australia — Trove"
    documentation_url = "https://trove.nla.gov.au/about/create-something/using-api"
    terms_note = ("Searches Trove's digitised newspapers with your key. Results come from Trove (trove.nla.gov.au) and link back to it. "
                  "Only search snippets are used: downloading full article text needs a separate exemption under Trove's terms.")
    record_kind = "newspaper article"
    requires_key = True
    key_signup = "create a Trove account → profile → “For developers” → apply for a key (reviewed; can take a few weeks; keys expire after 12 months)."
    max_per_minute = 60
    collection_seed_keys = ("trove",)
    coverage = {"countries": ["Australia"], "from": 1803, "to": 1954}
    ENDPOINT = "https://api.trove.nla.gov.au/v3/result"
    STATES = {"new south wales": "New South Wales", "victoria": "Victoria", "queensland": "Queensland", "south australia": "South Australia",
              "western australia": "Western Australia", "tasmania": "Tasmania", "northern territory": "Northern Territory", "act": "ACT"}

    def search(self, q: SearchQuery) -> SearchResult:
        self.check_key()
        text = _q(q)
        if q.year_from or q.year_to:
            yf, yt = q.year_from or q.year_to, q.year_to or q.year_from
            text += f" date:[{yf}-01-01T00:00:00Z TO {yt}-12-31T00:00:00Z]"
        params = {"category": "newspaper", "q": text, "n": max(1, min(100, q.page_size)), "encoding": "json", "reclevel": "brief", "sortby": "relevance"}
        if q.state and q.state.lower() in self.STATES:
            params["l-state"] = self.STATES[q.state.lower()]
        data = self._get_json(self.ENDPOINT, params, headers={"X-API-KEY": self.api_key or ""})
        cats = data.get("category") or []
        recs = ((cats[0] if cats else {}).get("records") or {})
        hits = []
        for a in recs.get("article") or []:
            t = a.get("title") or {}
            hits.append(Hit(item_id=str(a.get("id")), title=_strip_tags(a.get("heading")) or "Article", url=a.get("troveUrl"), date_text=a.get("date"),
                            snippet=_strip_tags(a.get("snippet")), place_text=t.get("state") if isinstance(t, dict) else None,
                            collection=(t.get("title") if isinstance(t, dict) else None) or "Trove", record_kind=self.record_kind,
                            extra={"attribution": "Data from Trove, National Library of Australia (trove.nla.gov.au)"}))
        return SearchResult(hits, recs.get("total"), "https://trove.nla.gov.au/search/category/newspapers")


class EuropeanaAdapter(SearchAdapter):
    key = "europeana"
    label = "Europeana (Search API)"
    provider = "Europeana"
    documentation_url = "https://europeana.atlassian.net/wiki/spaces/EF/pages/2385739812/Search+API+Documentation"
    terms_note = "Searches Europeana's aggregated metadata from European libraries and archives with your personal key. Metadata is CC0."
    record_kind = "catalog record"
    requires_key = True
    key_signup = "create a free Europeana account → “Manage API keys” → request a personal key (issued immediately)."
    max_per_minute = 30
    coverage = {}
    ENDPOINT = "https://api.europeana.eu/record/v2/search.json"

    def search(self, q: SearchQuery) -> SearchResult:
        self.check_key()
        params = [("query", _q(q)), ("rows", max(1, min(100, q.page_size))), ("start", 1 + (max(1, q.page) - 1) * q.page_size), ("profile", "standard")]
        if q.year_from or q.year_to:
            params.append(("qf", f"YEAR:[{q.year_from or q.year_to} TO {q.year_to or q.year_from}]"))
        if q.place or q.country:
            params.append(("qf", f"where:({q.place or q.country})"))
        data = self._get_json(self.ENDPOINT, dict(params) if len({k for k, _ in params}) == len(params) else params,
                              headers={"X-Api-Key": self.api_key or ""})
        hits = []
        for it in data.get("items") or []:
            hits.append(Hit(item_id=str(it.get("id")), title=_first(it.get("title")) or "Untitled", url=_first(it.get("edmIsShownAt")) or it.get("guid"),
                            date_text=_first(it.get("year")), snippet=(_first(it.get("dcDescription")) or "")[:600] or None,
                            place_text=_first(it.get("edmPlaceLabel")), collection=_first(it.get("dataProvider")), record_kind=self.record_kind))
        return SearchResult(hits, data.get("totalResults"), "https://www.europeana.eu/search?query=" + _q(q))
