"""External integrations.

Three distinct things, never conflated in the UI:
1. Searching this application's directory (local, see app/directory.py).
2. Opening a provider's own search (outbound link; pre-filled only when the URL
   pattern was verified — see build_search_link).
3. Retrieving external records through an implemented adapter that uses a
   documented, publicly offered API (see ADAPTERS).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from .base import IntegrationError, SearchAdapter  # noqa: F401
from .keyed import DPLAAdapter, EuropeanaAdapter, NARACatalogAdapter, TroveAdapter
from .census import IrishCensusAdapter, US1950CensusAdapter
from .loc import ChroniclingAmericaAdapter
from .open_apis import InternetArchiveTextAdapter, LOCBooksAdapter, PapersPastAdapter

ADAPTERS: dict[str, type[SearchAdapter]] = {a.key: a for a in (
    US1950CensusAdapter, IrishCensusAdapter, ChroniclingAmericaAdapter, LOCBooksAdapter, InternetArchiveTextAdapter, PapersPastAdapter,
    DPLAAdapter, NARACatalogAdapter, TroveAdapter, EuropeanaAdapter)}

PLACEHOLDERS = {"q", "surname", "given", "year_from", "year_to", "year", "place", "state"}


def build_search_link(collection: dict, query: dict) -> dict:
    """Return {url, prefilled, note}. Only verified templates are filled in."""
    base = collection.get("search_url") or collection.get("url")
    tpl = collection.get("search_url_template")
    if not (tpl and collection.get("search_link_verified")):
        return {"url": base, "prefilled": False,
                "note": "Opens the provider's search page. The URL format for pre-filled searches has not been verified, so copy the suggested query."}
    names = set(re.findall(r"{(\w+)}", tpl))
    if names - PLACEHOLDERS:
        return {"url": base, "prefilled": False, "note": "Search template has unknown placeholders; opening the search page instead."}
    values = {k: str(query.get(k) or "").strip() for k in PLACEHOLDERS}
    if not values["q"]:
        values["q"] = " ".join(x for x in [values["given"], values["surname"]] if x)
    values["state"] = values["state"].lower()
    if not values["year"] and values["year_from"] and values["year_to"]:
        try:
            values["year"] = str((int(values["year_from"]) + int(values["year_to"])) // 2)
        except ValueError:
            pass
    missing = [n for n in names if not values.get(n)]
    url = tpl
    for n in names:
        url = url.replace("{" + n + "}", quote_plus(values[n]))
    url = _drop_empty_params(url)
    return {"url": url, "prefilled": True,
            "note": "Pre-filled using a verified URL pattern." + (f" Empty fields: {', '.join(sorted(missing))}." if missing else "")}


def _drop_empty_params(url: str) -> str:
    """Remove query parameters left empty (and ones whose value is only '/' from an empty date range)."""
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if v.strip() not in ("", "/") and not v.endswith(":")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))
