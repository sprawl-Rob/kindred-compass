"""Family graph, record checklist, search links, name forms, census integrations and the stricter match checker."""
from urllib.parse import parse_qs, urlsplit

from app import nameequiv, placenorm
from app.integrations.base import SearchQuery
from app.integrations.census import IrishCensusAdapter, US1950CensusAdapter
from app.research import matching as mt

US = {"country": "United States", "region": "Massachusetts", "county": "Worcester"}


def test_place_cleanup():
    p = placenorm.parse("13 West, Fitchburg, Worcester, Massachusetts, USA")
    assert (p.town, p.county, p.state, p.detail, p.short()) == ("Fitchburg", "Worcester", "Massachusetts", "13 West", "Fitchburg, MA")
    assert placenorm.parse("Fitchburg Ward 4, Worcester, Massachusetts").town == "Fitchburg"
    assert placenorm.parse("Danville, Vermillion Co. IL").long() == "Danville, Vermillion County, Illinois"
    assert placenorm.parse("1725 D St, Sacramento, California").short() == "Sacramento, CA"
    assert placenorm.parse("Ireland (Irish Free State)").country == "Ireland"
    assert placenorm.parse("Sverige, Värmland, Sunne, Sweden").country == "Sweden"
    assert placenorm.parse("millbury ma").short() == "Millbury, MA"


def test_name_forms():
    assert "Andrew" in nameequiv.given_equivalents("Anders")
    assert "Maggie" in nameequiv.given_equivalents("Margaret") and "Delia" in nameequiv.given_equivalents("Bridget")
    assert "O'Sullivan" in nameequiv.surname_variants("Sullivan")
    assert "Bäcklund" not in nameequiv.surname_variants("Backlund") and "Becklund" in nameequiv.surname_variants("Backlund")
    assert nameequiv.nickname_in_quotes('Anders "Andrew" Gustav') == "Andrew"
    assert nameequiv.is_abbreviation("Wm") and not nameequiv.is_abbreviation("Fred")


def _tree(c):
    p = c.ok("post", "/api/projects", json={"name": "Family"})
    pid = p["id"]

    def person(given, surname, sex, claims):
        return c.ok("post", f"/api/projects/{pid}/persons", json={"names": [{"given": given, "surname": surname}], "sex": sex,
                                                                  "living_status": "deceased", "claims": claims})["id"]
    anders = person("Anders", "Backlund", "M", [{"claim_type": "birth", "date_text": "1836", "place": {"country": "Sweden"}},
                                                  {"claim_type": "immigration", "date_text": "1887"},
                                                  {"claim_type": "residence", "date_text": "1900", "place": {**US, "municipality": "Fitchburg"}},
                                                  {"claim_type": "death", "date_text": "14 Apr 1911", "place": {**US, "municipality": "Fitchburg"}}])
    oscar = person("Oscar", "Backlund", "M", [{"claim_type": "birth", "date_text": "3 Jun 1879", "place": {"country": "Sweden"}},
                                                  {"claim_type": "immigration", "date_text": "1889"},
                                                  {"claim_type": "residence", "date_text": "1910", "place": {**US, "municipality": "Fitchburg"}},
                                                  {"claim_type": "death", "date_text": "1933", "place": US}])
    hilda = person("Hilda", "Backlund", "F", [{"claim_type": "birth", "date_text": "1908", "place": {**US, "municipality": "Fitchburg"}},
                                                {"claim_type": "residence", "date_text": "1940", "place": {**US, "municipality": "Fitchburg"}}])
    john = person("John", "Sullivan", "M", [{"claim_type": "birth", "date_text": "1905", "place": {**US, "municipality": "Worcester"}}])
    c.ok("post", f"/api/projects/{pid}/claims", json={"person_id": oscar, "claim_type": "relationship", "relationship_type": "child", "related_person_id": anders})
    c.ok("post", f"/api/projects/{pid}/claims", json={"person_id": hilda, "claim_type": "relationship", "relationship_type": "child", "related_person_id": oscar})
    c.ok("post", f"/api/projects/{pid}/claims", json={"person_id": john, "claim_type": "relationship", "relationship_type": "spouse", "related_person_id": hilda})
    c.ok("post", f"/api/projects/{pid}/claims", json={"person_id": hilda, "claim_type": "marriage", "date_text": "1931", "place": {**US, "municipality": "Fitchburg"}})
    return pid, {"anders": anders, "oscar": oscar, "hilda": hilda, "john": john}


def test_tree_overview_checklist_and_home(make_client):
    c = make_client()
    pid, ids = _tree(c)
    t = c.ok("get", f"/api/projects/{pid}/tree?root={ids['hilda']}&depth=3")
    assert t["pedigree"]["name"] == "Hilda Backlund" and t["pedigree"]["parents"][0]["name"] == "Oscar Backlund"
    assert t["pedigree"]["parents"][0]["parents"][0]["name"] == "Anders Backlund"
    c.ok("put", f"/api/projects/{pid}/tree/home", json={"person_id": ids["hilda"]})
    assert c.ok("get", f"/api/projects/{pid}/tree")["root"] == ids["hilda"]

    o = c.ok("get", f"/api/persons/{ids['oscar']}/overview")
    items = {i["id"]: i for i in o["items"]}
    # Arrived 1889, died 1933: censuses 1900–1930 expected, 1880 not (still in Sweden), 1940 not (dead)
    assert {"census-1900", "census-1910", "census-1920", "census-1930"} <= set(items) and "census-1880" not in items and "census-1940" not in items
    assert items["census-1890"]["status"] == "lost"
    assert items["census-1900"]["expect"]["place"] == "Fitchburg, MA"
    assert {"immigration", "emigration", "naturalization", "draft-ww1", "death"} <= set(items)
    fs = [l for l in items["census-1920"]["searches"] if l["site"] == "FamilySearch" and not l.get("alt")][0]["url"]
    q = parse_qs(urlsplit(fs).query)
    assert q["q.surname"] == ["Backlund"] and q["f.collectionId"] == ["1488411"] and q["q.birthLikePlace"] == ["Sweden"]
    anc = [l for l in items["census-1920"]["searches"] if l["site"] == "Ancestry"][0]["url"]
    assert "/search/collections/6061/" in anc and "name=Oscar_Backlund" in anc and "residence=1920_fitchburg-worcester-massachusetts-usa" in anc
    assert o["family"]["parents"][0]["name"] == "Anders Backlund" and o["family"]["children"][0]["name"] == "Hilda Backlund"

    # A married woman is searched under her husband's surname after the marriage
    e = {i["id"]: i for i in c.ok("get", f"/api/persons/{ids['hilda']}/overview")["items"]}
    assert "q.surname=Sullivan" in e["census-1940"]["searches"][0]["url"] and "q.surname=Backlund" in e["census-1910"]["searches"][0]["url"]
    assert e["census-1950"]["auto"]["adapters"] == ["census_1950"]
    assert e["census-1910"]["expect"]["household"][0]["name"] == "Oscar Backlund"

    # Anders has no parents: the brick-wall pathway lists records that name parents
    a = {i["id"]: i for i in c.ok("get", f"/api/persons/{ids['anders']}/overview")["items"]}
    assert a["parents"]["paths"] and any(p["item"] == "emigration" for p in a["parents"]["paths"])
    h = c.ok("get", f"/api/projects/{pid}/home")
    assert h["root"]["id"] == ids["hilda"] and any(o["person"]["id"] == ids["anders"] for o in h["brick_walls"])


def test_planner_uses_married_names_nicknames_and_census(make_client, monkeypatch):
    c = make_client()
    pid, ids = _tree(c)
    pl = c.ok("post", f"/api/projects/{pid}/research/plan", json={"person_id": ids["hilda"], "options": {"adapters": ["census_1950", "loc_chronicling_america"], "max_queries": 40}})
    texts = [q["query"]["text"] for q in pl["queries"]]
    assert "Hilda Sullivan" in texts and "Mrs. John Sullivan" in texts
    cen = [q for q in pl["queries"] if q["adapter"] == "census_1950"]
    assert cen and cen[0]["query"]["state"] == "Massachusetts" and cen[0]["query"]["place"] == "Worcester"
    pl = c.ok("post", f"/api/projects/{pid}/research/plan", json={"person_id": ids["anders"], "options": {"adapters": ["census_1950", "loc_chronicling_america"], "max_queries": 40}})
    assert any(s["adapter"] == "census_1950" and "not alive" in s["reason"] for s in pl["skipped_archives"])
    death = [q for q in pl["queries"] if "death notice" in q["reason"]]
    assert death and death[0]["query"]["year_from"] == 1911 and death[0]["query"]["year_to"] == 1912


def test_census_1950_adapter_reads_household():
    page = {"total": 1, "results": [{"scheduleId": "9", "state": "Massachusetts", "county": "Worcester", "ed": "14-20", "image": "x.jpg",
                                     "names": [{"row": 8, "name": "Smith John"}, {"row": 9, "name": "Backlund HildaC."}, {"row": 10, "name": "Robert A."},
                                               {"row": 11, "name": "Mary"}, {"row": 12, "name": "Jones Peter"}],
                                     "transcribe": [], "highlight": {"names.name": ["Backlund HildaC.", "Backlund Carl"]}}]}
    calls = []
    a = US1950CensusAdapter(http_get=lambda url, params: calls.append(params) or page)
    r = a.search(SearchQuery(text="Hilda Backlund", state="Massachusetts", place="Worcester"))
    assert calls[0] == {"state": "MA", "name": "Backlund", "page": 1, "size": 25, "county": "Worcester"}
    assert len(r.hits) == 1   # "Carl" is not a form of Hilda
    h = r.hits[0]
    assert "Robert A. Backlund" in h.snippet and "Mary Backlund" in h.snippet and "Jones" not in h.snippet
    assert h.extra["match_place"] == "Massachusetts"


def test_irish_census_adapter_and_household():
    rows = [{"id": 1, "census_year": 1901, "county": "Kilkenny", "surname": "Kinsella", "firstname": "John", "townland": "Carrick", "ded": "Coolcullen",
             "age": 58, "relation_to_head": "Head of Family", "occupation": "Labourer", "birthplace": "Co Kilkenny", "image_group": "77", "house_number": "1"},
            {"id": 2, "census_year": 1901, "county": "Kilkenny", "surname": "Kinsella", "firstname": "Mary", "townland": "Carrick", "ded": "Coolcullen",
             "age": 56, "relation_to_head": "Wife", "birthplace": "Co Kilkenny", "image_group": "77", "house_number": "1"}]

    def http(url, params):
        if "image_group" in params:
            return {"results": rows, "meta": {"count": 2}}
        return {"results": rows[:1], "meta": {"count": 1}}
    a = IrishCensusAdapter(http_get=http)
    r = a.search(SearchQuery(text="John Kinsella", place="Kilkenny", year_from=1901, year_to=1901))
    assert r.hits[0].snippet.startswith("John Kinsella, aged 58. Head of Family")
    text = a.fetch_text(r.hits[0])
    assert "Mary Kinsella, aged 56. Wife" in text


def _prof(**kw):
    base = dict(givens=["john"], surnames=["sullivan"], variant_surnames=["osullivan"], year_from=1903, year_to=1941,
                places=["worcester", "massachusetts"], other_names=["john sullivan", "hilda sullivan"], birth=(1905, 1905), death=(1941, 1941),
                sex="M", given_equivs=["jack", "jno"], family_surnames=["sullivan", "backlund"])
    base.update(kw)
    return mt.Profile(**base)


def test_place_elsewhere_on_page_does_not_make_a_strong_match():
    """Regression: a Springfield sermon by 'Rev Leo Sullivan' was 'strong' because 'Worcester' appeared somewhere on the page."""
    p = _prof(given_equivs=["leo"])
    txt = ("were branded a lie by Rev Leo Sullivan in a sermon at the 8 o'clock mass at St Mary's church this morning. " + "filler " * 120 +
           "Worcester news follows.")
    r = mt.evaluate(p, "Springfield weekly Republican", None, txt, "1926-08-12", "springfield, hampden, massachusetts")
    assert r.strength != mt.STRONG and any("clergy" in x for x in r.reasons) and not any("Near the name" in x for x in r.reasons)


def test_nearby_evidence_nicknames_titles_and_new_names():
    p = _prof()
    txt = "WORCESTER. Jack Sullivan and his wife Hilda Sullivan of Grafton St. Mrs. Mary Sullivan and Carl Backlund attended."
    r = mt.evaluate(p, "Worcester Telegram", None, txt, "1930-06-01", "worcester, massachusetts")
    assert r.strength == mt.STRONG and any("“jack” for john" in x for x in r.reasons)
    assert "Carl Backlund" in r.mentions and "Mrs. Mary Sullivan" in r.mentions
    r = mt.evaluate(p, "Worcester Telegram", None, "Mrs. John Sullivan of Worcester entertained.", "1930-06-01", "worcester, massachusetts")
    assert r.strength != mt.STRONG
    r = mt.evaluate(p, "Telegram", None, "Miss John Sullivan of Worcester", "1930-06-01", "worcester, massachusetts")
    assert r.strength != mt.STRONG and any("is a man" in x for x in r.reasons)
    r = mt.evaluate(p, "Telegram", None, "John Sullivon of Worcester, machinist", "1930-06-01", "worcester, massachusetts")   # OCR slip
    assert any("one letter off" in x for x in r.reasons)


def test_estimated_birth_needs_two_corroborations():
    p = mt.Profile(["john"], ["kinsella"], [], 1821, 1950, [], ["mary kinsella"], (1821, 1850), None, "M", [], [], [], ["kinsella"], True)
    txt = "Household on the same census form: John Kinsella, aged 58. Head of Family. | Mary Kinsella, aged 56. Wife. | Bridget Kinsella, aged 18. Daughter."
    r = mt.evaluate(p, "1901 census of Ireland: John Kinsella", None, txt, "1901-03-31", "Co. Kilkenny, Ireland")
    assert r.strength == mt.POSSIBLE and any("only estimated" in x for x in r.reasons) and "Bridget Kinsella" in r.mentions
