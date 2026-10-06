"""Library of Congress — Chronicling America via the documented loc.gov JSON API.

Documentation: https://www.loc.gov/apis/json-and-yaml/  (append fo=json to loc.gov URLs);
parameters q, dates=YYYY/YYYY, fa=location_state:<state>, dl=page, c, sp, at verified 2026-10-05.
Since 2025 Chronicling America is served only through the loc.gov API (the legacy API is retired).
The API is public and needs no key. Documented limit: 20 requests/minute for the JSON API, and the
LoC legal page recommends no more than 10 requests/minute; this adapter enforces <= 10/minute.
Searches run only when the user asks (directly, or by starting a research run), one page at a time.
"""
from __future__ import annotations

import httpx

from .base import Hit, IntegrationError, SearchAdapter, SearchQuery, SearchResult

ENDPOINT = "https://www.loc.gov/collections/chronicling-america/"


def _first(v):
    if isinstance(v, list):
        return str(v[0]) if v else None
    return str(v) if v is not None else None


class ChroniclingAmericaAdapter(SearchAdapter):
    rate_group = "loc.gov"
    key = "loc_chronicling_america"
    label = "Chronicling America (Library of Congress API)"
    provider = "Library of Congress"
    documentation_url = "https://www.loc.gov/apis/json-and-yaml/"
    terms_note = ("Uses the public loc.gov JSON API for user-initiated searches, one page at a time, at most 10 requests a minute. "
                  "The Library of Congress does not clear copyright; items are for reference.")
    record_kind = "newspaper page"
    max_per_minute = 10
    supports_text = True
    verified_live = "2026-10-05"
    collection_seed_keys = ("loc-chronicling-america",)
    coverage = {"countries": ["United States"], "from": 1736, "to": 1963}

    def search(self, q: SearchQuery) -> SearchResult:
        text = (q.text or "").strip()
        if not text:
            raise IntegrationError("Enter words to search for.")
        if len(text) > 300:
            raise IntegrationError("Query is too long.")
        if q.phrase and " " in text and not text.startswith('"'):
            text = f'"{text}"'
        params = {"q": text, "fo": "json", "c": max(1, min(50, q.page_size)), "dl": "page", "at": "results,pagination", "sp": max(1, q.page)}
        if q.year_from or q.year_to:
            params["dates"] = f"{int(q.year_from or q.year_to)}/{int(q.year_to or q.year_from)}"
        if q.state:
            params["fa"] = f"location_state:{q.state.strip().lower()}"
        data = self._get_json(ENDPOINT, params, timeout=75)
        hits = []
        for r in data.get("results") or []:
            if not isinstance(r, dict):
                continue
            url = r.get("url") or r.get("id")
            hits.append(Hit(
                item_id=str(r.get("id") or url), title=_first(r.get("title")) or "Newspaper page", url=url, date_text=r.get("date"),
                snippet=(_first(r.get("description")) or "")[:600] or None,
                place_text=", ".join(x for x in [_first(r.get("location_city")), _first(r.get("location_county")), _first(r.get("location_state"))] if x) or None,
                collection=(_first(r.get("partof_title")) or "Chronicling America"), record_kind=self.record_kind,
                text_ref=str(r.get("id") or url), extra={"ocr_note": "Snippet is machine OCR text and may misread names."}))
        pag = data.get("pagination") or {}
        qurl = str(httpx.URL(ENDPOINT, params={k: v for k, v in params.items() if k not in ("fo", "at", "c")}))
        return SearchResult(hits, pag.get("of") or pag.get("total"), qurl)

    def fetch_text(self, hit: Hit) -> str | None:
        """Full OCR text of one page: page JSON (without q=, which is slow) → resource.fulltext_file → text service."""
        ref = (hit.text_ref or hit.item_id or "").replace("http://", "https://", 1)
        if not ref.startswith("https://www.loc.gov/resource/"):
            return None
        url, _, query = ref.partition("?")
        params = dict(p.split("=", 1) for p in query.split("&") if "=" in p and not p.startswith("q="))
        params.update({"fo": "json", "at": "page,resource,segments"})
        data = self._get_json(url, params, timeout=75)
        res = data.get("resource") or {}
        text_url = res.get("fulltext_file")
        if not text_url:
            for pg in data.get("page") or []:
                if isinstance(pg, dict) and pg.get("use") == "text" and pg.get("fulltext_service"):
                    text_url = pg["fulltext_service"]
                    break
        if not text_url or not text_url.startswith("https://tile.loc.gov/"):
            return None
        tdata = self._get_json(text_url, {}, timeout=60)
        if isinstance(tdata, dict):
            for v in tdata.values():
                if isinstance(v, dict) and v.get("full_text"):
                    return str(v["full_text"])
        return None

    def search_simple(self, body: dict) -> dict:
        """Used by the resource page's manual 'Live search' panel."""
        res = self.search(SearchQuery(text=body.get("q") or "", year_from=_int(body.get("year_from")), year_to=_int(body.get("year_to")),
                                      state=body.get("state") or None, page=_int(body.get("page")) or 1, page_size=20))
        return {"items": [{"title": h.title, "date": h.date_text, "url": h.url, "newspaper": h.collection, "location": h.place_text,
                           "snippet": h.snippet, "ocr_note": h.extra.get("ocr_note")} for h in res.hits],
                "total": res.total, "page": _int(body.get("page")) or 1, "query_url": res.query_url,
                "source": self.label, "retrieved_via": "Library of Congress public JSON API (loc.gov, fo=json)"}


def _int(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
