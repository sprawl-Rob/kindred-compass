"""Adapter interface for implemented external search integrations.

Every adapter wraps a *documented* public API whose terms allow user-initiated
automated searches. Adapters never scrape web pages, never log in, and never
bypass bot checks. Each one declares whether it needs a (free) API key, how fast
it may be called, and whether full item text can be fetched for match checking.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

USER_AGENT = "KindredCompass/1.0 (local genealogy research app; user-initiated searches)"


class IntegrationError(Exception):
    def __init__(self, message: str, retryable: bool = False, code: str = "error"):
        super().__init__(message)
        self.message, self.retryable, self.code = message, retryable, code


@dataclass
class SearchQuery:
    text: str                         # words or a name, as the provider's main search box would take
    phrase: bool = False              # search as an exact phrase where supported
    year_from: int | None = None
    year_to: int | None = None
    place: str | None = None          # free-text place
    state: str | None = None          # U.S. state (for facets that support it)
    country: str | None = None
    page: int = 1
    page_size: int = 20


@dataclass
class Hit:
    item_id: str
    title: str
    url: str | None
    date_text: str | None = None
    snippet: str | None = None
    place_text: str | None = None
    collection: str | None = None
    record_kind: str | None = None
    text_ref: str | None = None       # adapter-specific handle for fetch_text
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResult:
    hits: list
    total: int | None
    query_url: str | None
    request_note: str = ""


class Throttle:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.calls: deque = deque()
        self.lock = threading.Lock()

    def wait_time(self) -> float:
        with self.lock:
            now = time.monotonic()
            while self.calls and now - self.calls[0] > 60:
                self.calls.popleft()
            if len(self.calls) < self.per_minute:
                self.calls.append(now)
                return 0.0
            return 60 - (now - self.calls[0]) + 0.1

    def acquire(self, blocking: bool) -> None:
        while True:
            w = self.wait_time()
            if w <= 0:
                return
            if not blocking:
                raise IntegrationError(f"Rate limit for this archive reached; wait about {int(w) + 1} seconds.", retryable=True, code="rate_limit")
            time.sleep(min(w, 5))


class SearchAdapter:
    key: str = ""
    label: str = ""
    provider: str = ""
    documentation_url: str = ""
    terms_note: str = ""
    record_kind: str = "record"
    requires_key: bool = False
    optional_key: bool = False            # works without a key; a key raises limits
    key_signup: str | None = None         # how to obtain a key
    cache_days: int | None = None         # provider terms limit how long unsaved results may be kept
    rate_group: str | None = None         # adapters on the same host share one rate limit
    max_per_minute: int = 10
    supports_text: bool = False           # fetch_text available
    verified_live: str | None = None      # date the adapter was tested against the live API
    collection_seed_keys: tuple = ()      # directory entries this adapter searches
    coverage: dict = {}                   # {"countries": [...], "from": year, "to": year}

    _throttles: dict = {}

    def __init__(self, http_get: Callable[..., Any] | None = None, api_key: str | None = None, blocking: bool = False):
        self.http_get = http_get
        self.api_key = api_key
        self.blocking = blocking

    @classmethod
    def throttle(cls) -> Throttle:
        k = cls.rate_group or cls.key
        if k not in SearchAdapter._throttles:
            SearchAdapter._throttles[k] = Throttle(cls.max_per_minute)
        return SearchAdapter._throttles[k]

    def _get_json(self, url: str, params: dict, headers: dict | None = None, timeout: float = 60) -> Any:
        if self.http_get:
            data = self.http_get(url, params)
            if isinstance(data, str):
                raise IntegrationError(f"Unexpected response from {self.provider}.", code="bad_response")
            return data
        import httpx
        self.throttle().acquire(self.blocking)
        try:
            # An empty params dict would make httpx drop a query string already in the URL.
            r = httpx.get(url, params=params or None, headers={"User-Agent": USER_AGENT, **(headers or {})}, timeout=httpx.Timeout(timeout, connect=10),
                          follow_redirects=True)
        except httpx.TimeoutException:
            raise IntegrationError(f"{self.provider} did not respond in time. Try again.", retryable=True, code="timeout")
        except httpx.HTTPError:
            raise IntegrationError(f"Could not reach {self.provider}. Check your internet connection.", retryable=True, code="network")
        if r.status_code in (401, 403):
            raise IntegrationError(f"{self.provider} refused the request ({r.status_code})" +
                                   (" — check the API key in Settings → Archives." if self.requires_key else "."), code="auth")
        if r.status_code == 429:
            raise IntegrationError(f"{self.provider} rate limit reached. Wait a minute and try again.", retryable=True, code="rate_limit")
        if r.status_code >= 400:
            raise IntegrationError(f"{self.provider} returned an error ({r.status_code}).", retryable=r.status_code >= 500, code="http")
        try:
            return r.json()
        except ValueError:
            raise IntegrationError(f"Unexpected response from {self.provider}.", code="bad_response")

    def _get_text(self, url: str, params: dict | None = None, timeout: float = 60) -> str:
        if self.http_get:
            return self.http_get(url, params or {})
        import httpx
        self.throttle().acquire(self.blocking)
        try:
            r = httpx.get(url, params=params or None, headers={"User-Agent": USER_AGENT}, timeout=httpx.Timeout(timeout, connect=10), follow_redirects=True)
        except httpx.HTTPError:
            raise IntegrationError(f"Could not fetch text from {self.provider}.", retryable=True, code="network")
        if r.status_code >= 400:
            raise IntegrationError(f"{self.provider} returned an error ({r.status_code}) for the item text.", code="http")
        return r.text

    def check_key(self) -> None:
        if self.requires_key and not self.api_key:
            raise IntegrationError(f"{self.label} needs a free API key. Add it in Settings → Archives.", code="no_key")

    def search(self, q: SearchQuery) -> SearchResult:  # pragma: no cover - interface
        raise NotImplementedError

    def fetch_text(self, hit: Hit) -> str | None:
        return None

    @classmethod
    def describe(cls) -> dict:
        return {"key": cls.key, "label": cls.label, "provider": cls.provider, "documentation_url": cls.documentation_url,
                "terms_note": cls.terms_note, "requires_key": cls.requires_key, "optional_key": cls.optional_key, "key_signup": cls.key_signup,
                "record_kind": cls.record_kind, "supports_text": cls.supports_text, "verified_live": cls.verified_live,
                "max_per_minute": cls.max_per_minute, "coverage": cls.coverage, "collection_seed_keys": list(cls.collection_seed_keys)}
