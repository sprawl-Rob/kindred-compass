"""No-key archive integrations verified live on 2026-10-05 (notes: tools/research/search_apis_nokey.md).

- Library of Congress books (family & local histories) via loc.gov JSON, with whole-book OCR text.
- Internet Archive in-book full-text search via Open Library's search/inside API (snippets only;
  lending-only books are never fetched).
- Papers Past (New Zealand newspapers) via the DigitalNZ API v3 — key optional; a free key raises
  the shared anonymous limit. Metadata may be cached up to 30 days (unsaved results are trimmed after that).

Not integrated, by design: UK National Archives Discovery (terms: "do not cache or store" results),
WikiTree (no caching beyond a session), Digitalarkivet (no person-search API), FamilySearch (partner
approval only; not granted for personal use).
"""
from __future__ import annotations

import re

import httpx

from .base import Hit, IntegrationError, SearchAdapter, SearchQuery, SearchResult

MAX_TEXT_BYTES = 6_000_000


def _first(v):
    if isinstance(v, list):
        return str(v[0]) if v else None
    return str(v) if v is not None else None


def _q(q: SearchQuery) -> str:
    t = (q.text or "").strip()
    if not t:
        raise IntegrationError("Enter words to search for.")
    if q.phrase and " " in t and not t.startswith('"'):
        t = f'"{t}"'
    return t[:300]


class LOCBooksAdapter(SearchAdapter):
    rate_group = "loc.gov"
    key = "loc_books"
    label = "Library of Congress books (family & local histories)"
    provider = "Library of Congress"
    documentation_url = "https://www.loc.gov/apis/json-and-yaml/"
    terms_note = "Searches digitized books at the Library of Congress through its public JSON API (≤10 requests a minute) and reads their OCR text to find the name."
    record_kind = "published book"
    max_per_minute = 10
    supports_text = True
    verified_live = "2026-10-05"
    collection_seed_keys = ("loc-genealogy-guides",)
    coverage = {}
    ENDPOINT = "https://www.loc.gov/books/"

    def search(self, q: SearchQuery) -> SearchResult:
        params = {"q": _q(q), "fo": "json", "c": max(1, min(25, q.page_size)), "sp": max(1, q.page), "at": "results,pagination",
                  "fa": "online-format:online text"}
        data = self._get_json(self.ENDPOINT, params, timeout=75)
        hits = []
        for r in data.get("results") or []:
            if not isinstance(r, dict):
                continue
            res = (r.get("resources") or [{}])[0] or {}
            hits.append(Hit(item_id=str(r.get("id") or r.get("url")), title=_first(r.get("title")) or "Book", url=r.get("url") or r.get("id"),
                            date_text=r.get("date"), snippet=(_first(r.get("description")) or "")[:600] or None,
                            place_text=", ".join((r.get("location") or [])[:4]) or None, collection="Library of Congress books",
                            record_kind=self.record_kind, text_ref=res.get("text_file")))
        pag = data.get("pagination") or {}
        return SearchResult(hits, pag.get("of") or pag.get("total"), str(httpx.URL(self.ENDPOINT, params={"q": params["q"]})))

    def fetch_text(self, hit: Hit) -> str | None:
        if not hit.text_ref or not hit.text_ref.startswith("https://tile.loc.gov/"):
            return None
        t = self._get_text(hit.text_ref, timeout=90)
        return t[:MAX_TEXT_BYTES]


class InternetArchiveTextAdapter(SearchAdapter):
    key = "ia_fulltext"
    label = "Internet Archive books — search inside (via Open Library)"
    provider = "Internet Archive / Open Library"
    documentation_url = "https://openlibrary.org/dev/docs/api/search_inside"
    terms_note = ("Searches the text inside digitized books (city directories, county and family histories) using Open Library's search-inside API, "
                  "at most one request per second. Only the snippets returned are used; lending-only books are linked, never downloaded.")
    record_kind = "published book (page)"
    max_per_minute = 30
    verified_live = "2026-10-05"
    coverage = {}
    ENDPOINT = "https://openlibrary.org/search/inside.json"

    def search(self, q: SearchQuery) -> SearchResult:
        params = {"q": _q(q), "limit": max(1, min(50, q.page_size)), "page": max(1, q.page)}
        data = self._get_json(self.ENDPOINT, params, timeout=90)
        hits_in = ((data.get("hits") or {}).get("hits")) or []
        hits = []
        for h in hits_in:
            f = h.get("fields") or {}
            ident = _first(f.get("identifier"))
            year = _first(f.get("meta_year"))
            if q.year_from and year and year.isdigit() and int(year) < q.year_from - 1:
                continue   # books are usually published after the events; only drop clearly-too-early ones
            pages = f.get("page_num") or []
            page = pages[0][0] if pages and isinstance(pages[0], list) and pages[0] else (pages[0] if pages else None)
            snippets = [re.sub(r"\{\{\{|\}\}\}", "", s) for s in (h.get("highlight") or {}).get("text") or []]
            avail = (h.get("availability") or {}).get("status")
            url = f"https://archive.org/details/{ident}" + (f"/page/n{page}" if page else "")
            hits.append(Hit(item_id=f"{ident}#{page}", title=_first(f.get("meta_title")) or ident or "Book", url=url, date_text=year,
                            snippet=" … ".join(snippets)[:900] or None, collection="Internet Archive", record_kind=self.record_kind,
                            extra={"availability": avail, "page": page}))
        total = (data.get("hits") or {}).get("total")
        total = total.get("value") if isinstance(total, dict) else total
        return SearchResult(hits, total, f"https://openlibrary.org/search/inside?q={params['q']}")


class PapersPastAdapter(SearchAdapter):
    key = "papers_past"
    label = "Papers Past (via DigitalNZ API)"
    provider = "DigitalNZ / National Library of New Zealand"
    documentation_url = "https://digitalnz.org/developers/api-docs-v3"
    terms_note = ("Searches New Zealand newspapers in Papers Past through the DigitalNZ API and links to each item's source page. Works without a key "
                  "(a shared national limit applies); a free DigitalNZ key is recommended. Unsaved results are trimmed after 30 days, as the terms require.")
    record_kind = "newspaper article"
    max_per_minute = 30
    supports_text = True
    optional_key = True
    key_signup = "optional: register free at https://digitalnz.org/developers for a personal key (raises the request limit)."
    verified_live = "2026-10-05"
    collection_seed_keys = ("papers-past",)
    coverage = {"countries": ["New Zealand"], "from": 1839, "to": 1999}
    cache_days = 30
    ENDPOINT = "https://api.digitalnz.org/v3/records.json"

    def search(self, q: SearchQuery) -> SearchResult:
        params = [("text", _q(q) + (f" {q.place}" if q.place else "")), ("and[primary_collection][]", "Papers Past"),
                  ("per_page", max(1, min(50, q.page_size))), ("page", max(1, q.page)),
                  ("fields", "id,title,display_date,date,landing_url,source_url,description,fulltext,collection_title")]
        if q.year_from or q.year_to:
            a, b = int(q.year_from or q.year_to), int(q.year_to or q.year_from)
            decades = list(range(a // 10 * 10, b // 10 * 10 + 1, 10))[:15]
            params += [("or[decade][]", str(d)) for d in decades]
        headers = {"Authentication-Token": self.api_key} if self.api_key else {}
        data = self._get_json(self.ENDPOINT, params, headers=headers)
        s = data.get("search") or {}
        hits = []
        for r in s.get("results") or []:
            text = r.get("fulltext") or ""
            hits.append(Hit(item_id=str(r.get("id")), title=r.get("title") or "Article", url=r.get("landing_url") or r.get("source_url"),
                            date_text=(r.get("date") or [None])[0] if isinstance(r.get("date"), list) else (r.get("display_date") or r.get("date")),
                            snippet=(r.get("description") or text[:400] or None), collection=_first(r.get("collection_title")) or "Papers Past",
                            record_kind=self.record_kind, extra={"text": text[:200000]} if text else {}))
        return SearchResult(hits, s.get("result_count"), "https://paperspast.natlib.govt.nz/newspapers?query=" + _q(q))

    def fetch_text(self, hit: Hit) -> str | None:
        return (hit.extra or {}).get("text") or None
