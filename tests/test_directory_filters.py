"""Resource filtering by geography, dates, access, record type; unknown coverage; partial overlap."""
from app import coverage as cov
from tests.conftest import by_name


def search(client, **f):
    return client.ok("post", "/api/directory/search", json=f)


def test_geography_filter_excludes_other_countries_but_keeps_worldwide(client):
    r = search(client, country="Norway")
    names = {c["name"] for g in r["groups"].values() for c in g}
    assert "Digitalarkivet" in names
    assert "ScotlandsPeople" not in names  # known coverage elsewhere → excluded
    g, fs = by_name(r["groups"], "FamilySearch Historical Records (name search)")
    assert g == "unknown" or g == "partial"  # worldwide, not itemised: never a confirmed match


def test_state_level_and_county_level_matching(client):
    r = search(client, country="United States", region="MA", county="Worcester")
    g, worcester = by_name(r["groups"], "Worcester Probate and Family Court")
    assert worcester is not None
    assert worcester["coverage"]["geo"] == "match"
    # A different county's repository is excluded
    _, cook = by_name(r["groups"], "Cook County Clerk genealogy records")
    assert cook is None


def test_unknown_coverage_is_neither_match_nor_absence(client):
    r = search(client, country="United States", region="Massachusetts", year_from=1870, year_to=1890)
    g, worcester = by_name(r["groups"], "Worcester Probate and Family Court")
    assert g == "unknown"  # dates not recorded
    assert worcester["coverage"]["dates"] == "unknown"


def test_partial_date_overlap(client):
    r = search(client, country="Ireland", year_from=1895, year_to=1905)
    g, nai = by_name(r["groups"], "National Archives of Ireland census search")
    assert g == "partial"
    assert "overlap" in nai["coverage"]["dates_why"].lower()


def test_known_gap_is_reported():
    status, why = cov.date_match([{"from": 1821, "to": 1926}], 1870, 1880, [{"from": 1861, "to": 1891, "label": "lost censuses"}])
    assert status == cov.PARTIAL and "gap" in why


def test_date_match_states():
    assert cov.date_match([{"from": 1850, "to": 1900}], 1860, 1870)[0] == cov.MATCH
    assert cov.date_match([{"from": 1850, "to": 1900}], 1890, 1910)[0] == cov.PARTIAL
    assert cov.date_match([{"from": 1850, "to": 1900}], 1901, 1910)[0] == cov.NONE
    assert cov.date_match([], 1901, 1910)[0] == cov.UNKNOWN


def test_record_type_filter(client):
    r = search(client, record_types=["passenger_lists"])
    names = {c["name"] for g in ("match", "partial", "unknown") for c in r["groups"][g]}
    assert "NARA Passenger Arrival Records" in {c["name"] for c in r["groups"]["guidance"]}  # guides grouped separately
    assert "Ellis Island Foundation passenger search" in names
    assert "FreeBMD (civil registration index)" not in names


def test_access_filter_hides_but_reports(client):
    r = search(client, access="free")
    hidden = {h["name"] for h in r["hidden_by_preferences"]}
    assert "Archion (Protestant church books)" in hidden  # subscription
    assert all(h["reason"] for h in r["hidden_by_preferences"])
    visible = {c["name"] for g in r["groups"].values() for c in g}
    assert "Archion (Protestant church books)" not in visible


def test_text_search_matches_terminology(client):
    r = search(client, q="Kirchenbücher")
    names = {c["name"] for g in r["groups"].values() for c in g}
    assert "Archion (Protestant church books)" in names


def test_providers_and_collections_are_separate(client):
    r = search(client, q="FamilySearch")
    fs = [c for g in r["groups"].values() for c in g if c["provider_name"] == "FamilySearch"]
    kinds = {c["name"] for c in fs}
    assert {"FamilySearch Historical Records (name search)", "FamilySearch Full-Text Search", "FamilySearch Catalog",
            "FamilySearch Research Wiki"} <= kinds
    assert len({c["provider_id"] for c in fs}) == 1


def test_badges_are_honest(client):
    r = search(client, q="Matricula")
    _, m = by_name(r["groups"], "Matricula (Catholic parish registers)")
    labels = {b["label"] for b in m["badges"]}
    assert "Browse only" in labels
    r = search(client, q="MyHeritage")
    _, mh = by_name(r["groups"], "MyHeritage historical records search")
    assert "Needs verification" in {b["label"] for b in mh["badges"]}
