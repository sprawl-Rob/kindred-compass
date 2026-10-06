"""Coverage matching for geography and dates.

Every match function returns a tri-state-plus result so that *unknown* coverage
is never reported as either a match or a confirmed absence:

    "match"    – coverage explicitly includes the requested place/years
    "partial"  – overlaps part of the requested range, or matches at a broader level
    "unknown"  – the directory does not know this collection's coverage
    "none"     – coverage is known and does not include the request
"""
from __future__ import annotations

from dataclasses import dataclass

MATCH, PARTIAL, UNKNOWN, NONE = "match", "partial", "unknown", "none"

# Common aliases so "USA" and "United States" match. Kept deliberately small and explicit.
COUNTRY_ALIASES = {
    "usa": "united states", "us": "united states", "u.s.": "united states", "u.s.a.": "united states",
    "united states of america": "united states", "america": "united states",
    "uk": "united kingdom", "great britain": "united kingdom", "britain": "united kingdom",
    "nz": "new zealand", "aotearoa": "new zealand",
    "deutschland": "germany", "norge": "norway", "éire": "ireland", "eire": "ireland",
}
# Constituent countries are matched both as themselves and as part of the UK.
UK_PARTS = {"england", "wales", "scotland", "northern ireland"}

US_STATE_ABBR = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california", "co": "colorado",
    "ct": "connecticut", "de": "delaware", "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas", "ky": "kentucky", "la": "louisiana",
    "me": "maine", "md": "maryland", "ma": "massachusetts", "mi": "michigan", "mn": "minnesota",
    "ms": "mississippi", "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico", "ny": "new york", "nc": "north carolina",
    "nd": "north dakota", "oh": "ohio", "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania",
    "ri": "rhode island", "sc": "south carolina", "sd": "south dakota", "tn": "tennessee", "tx": "texas",
    "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
}


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = " ".join(str(s).strip().lower().replace(",", " ").split())
    for suffix in (" county", " co.", " parish", " shire"):
        if s.endswith(suffix) and len(s) > len(suffix) + 1:
            s = s[: -len(suffix)]
    return s


def norm_country(s: str | None) -> str:
    n = norm(s)
    return COUNTRY_ALIASES.get(n, n)


def norm_region(s: str | None) -> str:
    n = norm(s)
    return US_STATE_ABBR.get(n, n)


@dataclass
class PlaceQuery:
    country: str | None = None
    region: str | None = None
    county: str | None = None
    municipality: str | None = None
    historical_jurisdiction: str | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "PlaceQuery":
        d = d or {}
        return cls(d.get("country"), d.get("region"), d.get("county"), d.get("municipality"), d.get("historical_jurisdiction"))

    def is_empty(self) -> bool:
        return not any([self.country, self.region, self.county, self.municipality, self.historical_jurisdiction])

    def label(self) -> str:
        parts = [self.municipality, self.county and f"{self.county} County" if self.country and norm_country(self.country) == "united states" else self.county,
                 self.region, self.country]
        return ", ".join(p for p in parts if p)


def _country_eq(a: str, b: str) -> bool:
    a, b = norm_country(a), norm_country(b)
    if not a or not b:
        return False
    if a == b:
        return True
    # A UK-wide collection covers England, Wales, Scotland, NI queries.
    return (a == "united kingdom" and b in UK_PARTS) or (b == "united kingdom" and a in UK_PARTS)


def geo_match(geo_scope: str, geo: list[dict], q: PlaceQuery) -> tuple[str, str]:
    """Return (status, explanation)."""
    if q.is_empty():
        return MATCH, "No place specified"
    if geo_scope == "worldwide":
        return PARTIAL, "Collection is not limited to one place; coverage of this place is not itemised"
    if geo_scope == "unknown" or not geo:
        return UNKNOWN, "Geographic coverage not recorded in the directory"

    best = (NONE, "Coverage does not include this place")
    rank = {NONE: 0, PARTIAL: 1, MATCH: 2}
    for g in geo:
        status, why = _match_one(g, q)
        if rank[status] > rank[best[0]]:
            best = (status, why)
        if status == MATCH:
            break
    return best


def _match_one(g: dict, q: PlaceQuery) -> tuple[str, str]:
    gc, gr, gk, gm = g.get("country"), g.get("region"), g.get("county"), g.get("municipality")
    ghj = g.get("historical_jurisdiction")

    # Historical jurisdiction match counts as a direct match.
    if q.historical_jurisdiction and ghj and norm(q.historical_jurisdiction) == norm(ghj):
        return MATCH, f"Covers historical jurisdiction {ghj}"

    if q.country and gc and not _country_eq(q.country, gc):
        return NONE, "Different country"
    if not q.country and gc and not (q.region or q.county or q.municipality):
        return NONE, "Different country"

    # Walk down the hierarchy. A collection that covers a whole country fully
    # covers every place inside it (if it says it covers the whole country).
    levels = [("region", gr, q.region, norm_region), ("county", gk, q.county, norm), ("municipality", gm, q.municipality, norm)]
    covered_label = gc or ""
    for lvl, gv, qv, fn in levels:
        if gv is None or gv == "":
            # Collection covers the whole of the previous level.
            if qv:
                return MATCH, f"Covers all of {covered_label}" if covered_label else "Covers this area"
            return MATCH, f"Covers {covered_label}" if covered_label else "Covers this area"
        if not qv:
            # Collection is narrower than the question (e.g. one county, question names a state).
            return PARTIAL, f"Covers part of the requested area ({gv})"
        if fn(gv) != fn(qv):
            return NONE, f"Covers a different {lvl} ({gv})"
        covered_label = gv
    return MATCH, f"Covers {covered_label}"


def date_match(ranges: list[dict], year_from: int | None, year_to: int | None, gaps: list[dict] | None = None) -> tuple[str, str]:
    if year_from is None and year_to is None:
        return MATCH, "No years specified"
    if not ranges:
        return UNKNOWN, "Date coverage not recorded in the directory"
    qf = year_from if year_from is not None else -10_000
    qt = year_to if year_to is not None else 10_000
    if qf > qt:
        qf, qt = qt, qf
    best = (NONE, "Known date coverage does not include these years")
    for r in ranges:
        rf = r.get("from") if r.get("from") is not None else -10_000
        rt = r.get("to") if r.get("to") is not None else 10_000
        if rf <= qf and rt >= qt:
            best = (MATCH, f"Covers {_range_label(r)}")
            break
        if rf <= qt and rt >= qf:
            lo, hi = max(rf, qf), min(rt, qt)
            best = (PARTIAL, f"Partly overlaps: covers {_range_label(r)}; overlap {lo}–{hi}")
    if best[0] in (MATCH, PARTIAL) and gaps:
        for gap in gaps:
            gf, gt = gap.get("from"), gap.get("to")
            if gf is not None and gt is not None and gf <= qt and gt >= qf:
                note = gap.get("label") or f"{gf}–{gt}"
                return PARTIAL, best[1] + f"; known gap: {note}"
    return best


def _range_label(r: dict) -> str:
    f, t = r.get("from"), r.get("to")
    lab = r.get("label")
    span = f"{f if f is not None else '…'}–{t if t is not None else 'present'}"
    return f"{span} ({lab})" if lab else span


def combine(geo_status: str, date_status: str) -> str:
    """Combine geography + date into one overall coverage status."""
    if NONE in (geo_status, date_status):
        return NONE
    if UNKNOWN in (geo_status, date_status):
        return UNKNOWN
    if PARTIAL in (geo_status, date_status):
        return PARTIAL
    return MATCH
