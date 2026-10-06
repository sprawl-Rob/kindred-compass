"""Turn the free-text places found in family trees into a clean town / county / state / country.

Family-tree places are messy ("13 West, Fitchburg, Worcester, Massachusetts, USA",
"Fitchburg Ward 2, Worcester, Massachusetts", "Danville, Vermillion Co. IL", "Stewart, NE").
Everything here is deterministic and conservative: when a part can't be recognised it is kept
as written, never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
STATE_ABBR = {v.lower(): k for k, v in US_STATES.items()}
_STATE_ALIASES = {"mass": "MA", "mass.": "MA", "penn": "PA", "penna": "PA", "calif": "CA", "conn": "CT", "wis": "WI", "wisc": "WI",
                  "minn": "MN", "mich": "MI", "ill": "IL", "ind": "IN", "kans": "KS", "nebr": "NE", "oreg": "OR", "tex": "TX",
                  "wash": "WA", "n.y.": "NY", "n.y": "NY", "n.h.": "NH", "r.i.": "RI", "n.j.": "NJ", "vt.": "VT", "me.": "ME"}

US_NAMES = {"usa", "u.s.a.", "u.s.a", "us", "u.s.", "united states", "united states of america", "america"}
COUNTRY_ALIASES = {
    "deutschland": "Germany", "germany": "Germany", "prussia": "Germany", "preussen": "Germany", "bavaria": "Germany", "bayern": "Germany",
    "sverige": "Sweden", "sweden": "Sweden", "norge": "Norway", "norway": "Norway", "danmark": "Denmark", "denmark": "Denmark",
    "suomi": "Finland", "finland": "Finland", "ireland": "Ireland", "eire": "Ireland", "éire": "Ireland", "northern ireland": "Northern Ireland",
    "england": "England", "scotland": "Scotland", "wales": "Wales", "united kingdom": "United Kingdom", "uk": "United Kingdom",
    "great britain": "United Kingdom", "canada": "Canada", "france": "France", "italy": "Italy", "italia": "Italy", "poland": "Poland",
    "polska": "Poland", "austria": "Austria", "österreich": "Austria", "switzerland": "Switzerland", "schweiz": "Switzerland",
    "netherlands": "Netherlands", "holland": "Netherlands", "belgium": "Belgium", "russia": "Russia", "mexico": "Mexico",
    "czech republic": "Czech Republic", "bohemia": "Czech Republic", "hungary": "Hungary", "luxembourg": "Luxembourg",
}
CANADA_PROVINCES = {"ontario", "quebec", "québec", "nova scotia", "new brunswick", "manitoba", "british columbia",
                    "prince edward island", "saskatchewan", "alberta", "newfoundland"}


@dataclass
class Place:
    raw: str
    detail: str | None = None       # street address, ward, institution — kept, not used for searching
    town: str | None = None
    county: str | None = None
    state: str | None = None        # full state / province name
    country: str | None = None

    @property
    def is_us(self) -> bool:
        return self.country == "United States"

    def short(self) -> str:
        """Compact label: 'Fitchburg, MA', 'Worcester County, MA', 'Sweden'."""
        if self.is_us:
            ab = STATE_ABBR.get((self.state or "").lower())
            st = ab or self.state
            if self.town:
                return f"{self.town}, {st}" if st else self.town
            if self.county:
                return f"{self.county} County, {st}" if st else f"{self.county} County"
            return self.state or "United States"
        parts = [self.town, self.state, self.country]
        out = [p for p in parts if p]
        return ", ".join(dict.fromkeys(out)) or self.raw

    def long(self) -> str:
        if self.is_us:
            return ", ".join(x for x in [self.town, self.county and f"{self.county} County", self.state] if x) or self.raw
        return ", ".join(dict.fromkeys(x for x in [self.town, self.county, self.state, self.country] if x)) or self.raw

    def as_dict(self) -> dict:
        d = asdict(self)
        d["short"] = self.short()
        d["long"] = self.long()
        return d


def _state(tok: str) -> str | None:
    t = tok.strip().strip(".").lower()
    t2 = tok.strip().lower()
    if t in STATE_ABBR:
        return US_STATES[STATE_ABBR[t]]
    if tok.strip().upper().strip(".") in US_STATES and len(tok.strip().strip(".")) == 2:
        return US_STATES[tok.strip().upper().strip(".")]
    if t2 in _STATE_ALIASES:
        return US_STATES[_STATE_ALIASES[t2]]
    if t in _STATE_ALIASES:
        return US_STATES[_STATE_ALIASES[t]]
    # OCR/typing damage such as "OHnia": a known abbreviation followed by junk is not trusted
    return None


_WARD = re.compile(r"^(.*?)\s+(?:ward|wd\.?|precinct|district)\s*\d+\w*$", re.IGNORECASE)
_COUNTY = re.compile(r"^(.*?)\s+(?:county|co\.?|parish)$", re.IGNORECASE)


def _clean_town(tok: str) -> tuple[str | None, str | None]:
    """Return (town, detail). Strips ward numbers; treats numbered street addresses as detail."""
    t = tok.strip()
    if not t:
        return None, None
    m = _WARD.match(t)
    if m:
        return m.group(1).strip(), t
    if _is_detail(t):
        return None, t
    return (t.title() if t.islower() else t), None


def _is_detail(t: str) -> bool:
    """A street address or an institution, not a town. ("Main St" is an address; "St. Elizabeth" is a town.)"""
    t = t.strip()
    return bool(re.match(r"^\d", t)
                or re.search(r"\s(st|street|ave|avenue|rd|road|pl|place|lane|ln|drive|dr|blvd|ct|court|ter|terrace)\.?$", t, re.IGNORECASE)
                or re.search(r"\b(box|hospital|home|asylum|cemetery|farm|park|memorial|gardens|church|chapel|school|hotel|ship)\b", t, re.IGNORECASE))


def parse(raw: str | None) -> Place:
    raw = (raw or "").strip()
    p = Place(raw=raw)
    if not raw:
        return p
    # "Danville, Vermillion Co. IL" / "Anaheim California" — split a trailing state off the last part
    parts = [x.strip() for x in raw.split(",")]
    parts = [x for x in parts if x]
    if parts:
        last = parts[-1]
        m = re.match(r"^(.*?)[\s.]+([A-Za-z.]{2,})$", last)
        if m and _state(m.group(2)) and not _state(last) and last.lower() not in COUNTRY_ALIASES and last.lower() not in US_NAMES:
            parts = parts[:-1] + [m.group(1).strip(), m.group(2)]
    if not parts:
        return p
    # Country
    if len(parts) > 1 and parts[0].lower() in COUNTRY_ALIASES and parts[-1].lower() in COUNTRY_ALIASES:
        parts = parts[1:]   # "Sverige, Värmland, Sunne, Sweden"
    low = re.sub(r"\s*\(.*\)$", "", parts[-1]).lower()
    if low in US_NAMES:
        p.country = "United States"
        parts = parts[:-1]
    elif low in COUNTRY_ALIASES:
        p.country = COUNTRY_ALIASES[low]
        parts = parts[:-1]
    # US state
    if parts and p.country in (None, "United States"):
        st = _state(parts[-1])
        if st:
            p.state, p.country = st, "United States"
            parts = parts[:-1]
    if parts and p.country is None and parts[-1].lower() in CANADA_PROVINCES:
        p.state, p.country = parts[-1], "Canada"
        parts = parts[:-1]
    if p.country is None and not parts:
        return p
    if p.country is None:
        # Not recognisably anywhere; keep as written (e.g. "Stockholm", "On the ship Werra")
        if len(parts) == 1:
            p.town, p.detail = _clean_town(parts[0])
            if p.town is None and p.detail is None:
                p.town = parts[0]
            return p
    if p.is_us:
        # remaining: [detail..., town, county] or [town] or [county]
        if parts:
            m = _COUNTY.match(parts[-1])
            if m:
                p.county = m.group(1).strip()
                parts = parts[:-1]
            elif len(parts) >= 2 and not _is_detail(parts[-2]):
                p.county = parts[-1].strip()
                parts = parts[:-1]
        if parts:
            town, detail = _clean_town(parts[-1])
            if town is None and len(parts) >= 2:
                # last part was an address; the town is not separately recorded
                detail = ", ".join(parts)
            elif len(parts) >= 2:
                detail = ", ".join(parts[:-1] + ([detail] if detail else []))
            p.town, p.detail = town, detail
        if p.county:
            p.county = re.sub(r"\s+(?:county|co\.?)$", "", p.county, flags=re.IGNORECASE).strip()
            if p.county.isupper():
                p.county = p.county.title()
    else:
        # foreign: [detail..., town, region]
        if len(parts) >= 2:
            p.state = parts[-1]
            town, detail = _clean_town(parts[-2])
            p.town = town
            p.detail = ", ".join(parts[:-2] + ([detail] if detail else [])) or None
        elif parts:
            p.town, p.detail = _clean_town(parts[0])
    return p


def from_row(place: dict | None) -> Place:
    """Prefer the free-text name (what the tree says); fall back to the structured columns."""
    if not place:
        return Place(raw="")
    if place.get("name"):
        return parse(place["name"])
    return parse(", ".join(x for x in [place.get("municipality"), place.get("county"), place.get("region"), place.get("country")] if x))
