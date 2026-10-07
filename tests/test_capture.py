"""Bringing a record found on another site into the tree: pasted text or a clipped page → source, facts, relatives."""
from app import capture

ANCESTRY = """1920 United States Federal Census
Name\tOscar Lindqvist
Age\t42
Birth Year\tabt 1878
Birthplace\tSweden
Home in 1920\tFitchburg Ward 2, Worcester, Massachusetts
Residence Date\t1920
Immigration Year\t1890
Relation to Head of House\tHead
Marital Status\tMarried
Spouse's Name\tGreta Lindqvist
Occupation\tLaborer
Household Members\tName\tAge
Oscar Lindqvist\t42
Greta Lindqvist\t41
Hilda Lindqvist\t12
Harold Lindqvist\t9
"""
FAMILYSEARCH = """Oscar Lindqvist
United States Census, 1920
Name\tOscar Lindqvist
Sex\tMale
Age\t42
Event Date\t1920
Event Place\tFitchburg Ward 2, Worcester, Massachusetts, United States
Relationship to Head of Household\tHead
Household\tRelationship\tSex\tAge\tBirthplace
Oscar Lindqvist\tHead\tM\t42\tSweden
Greta Lindqvist\tWife\tF\t41\tSweden
Hilda Lindqvist\tDaughter\tF\t12\tMassachusetts
"""


def test_parse_ancestry_and_familysearch_layouts():
    a = capture.parse(ANCESTRY, "https://www.ancestry.com/discoveryui-content/view/1:6061", "Oscar Lindqvist - 1920 United States Federal Census - Ancestry")
    assert (a["kind"], a["year"], a["site"]) == ("census", 1920, "Ancestry")
    assert a["fields"]["residence_place"].startswith("Fitchburg") and a["fields"]["immigration"] == "1890"
    assert [r["name"] for r in a["household"]] == ["Oscar Lindqvist", "Greta Lindqvist", "Hilda Lindqvist", "Harold Lindqvist"]
    f = capture.parse(FAMILYSEARCH, "https://www.familysearch.org/ark:/61903/1:1:X", "United States Census, 1920")
    assert f["year"] == 1920 and f["site"] == "FamilySearch"
    assert [(r["name"], r["relation"]) for r in f["household"]][1] == ("Greta Lindqvist", "wife")


def _family(c):
    pid = c.ok("post", "/api/projects", json={"name": "Capture"})["id"]
    oscar = c.ok("post", f"/api/projects/{pid}/persons", json={"names": [{"given": "Oscar", "surname": "Lindqvist"}], "sex": "M", "living_status": "deceased",
                                                                "claims": [{"claim_type": "birth", "date_text": "1878", "place": {"country": "Sweden"}},
                                                                           {"claim_type": "residence", "date_text": "1910", "place": {"country": "United States", "region": "Massachusetts", "municipality": "Fitchburg"}}]})["id"]
    greta = c.ok("post", f"/api/projects/{pid}/persons", json={"names": [{"given": "Margareta", "surname": "Holm"}], "sex": "F", "living_status": "deceased"})["id"]
    hilda = c.ok("post", f"/api/projects/{pid}/persons", json={"names": [{"given": "Hilda", "surname": "Lindqvist"}], "sex": "F", "living_status": "deceased",
                                                                "claims": [{"claim_type": "birth", "date_text": "1907"}]})["id"]
    c.ok("post", f"/api/projects/{pid}/claims", json={"person_id": oscar, "claim_type": "relationship", "relationship_type": "spouse", "related_person_id": greta})
    c.ok("post", f"/api/projects/{pid}/claims", json={"person_id": hilda, "claim_type": "relationship", "relationship_type": "child", "related_person_id": oscar})
    return pid, oscar, greta, hilda


def test_preview_and_save_turn_the_record_into_source_facts_and_people(make_client):
    c = make_client()
    pid, oscar, greta, hilda = _family(c)
    pv = c.ok("post", f"/api/persons/{oscar}/capture/preview", json={"text": ANCESTRY, "url": "https://www.ancestry.com/x", "title": "1920 United States Federal Census"})
    assert pv["source"]["title"] == "1920 United States Federal Census" and "Ancestry" in pv["source"]["citation"]
    kinds = {f["claim_type"]: f for f in pv["facts"]}
    assert kinds["residence"]["date_text"] == "1920" and kinds["immigration"]["date_text"] == "1890" and kinds["occupation"]["value_text"] == "Laborer"
    ppl = {p["name"]: p for p in pv["people"]}
    assert ppl["Greta Lindqvist"]["match"]["id"] == greta and ppl["Greta Lindqvist"]["relationship"] == "spouse"   # Greta = Margareta
    assert ppl["Hilda Lindqvist"]["match"]["id"] == hilda and ppl["Hilda Lindqvist"]["born"] is None              # already has a birth year
    assert ppl["Harold Lindqvist"]["action"] == "add" and ppl["Harold Lindqvist"]["relationship"] == "child" and ppl["Harold Lindqvist"]["relationship_inferred"]
    before = c.ok("get", f"/api/persons/{oscar}/overview")
    assert next(i for i in before["items"] if i["id"] == "census-1920")["status"] == "missing"
    r = c.ok("post", f"/api/persons/{oscar}/capture/save", json={"source": pv["source"], "facts": pv["facts"], "people": pv["people"], "text": ANCESTRY})
    assert r["facts"] == 4 and r["people_added"] == 1 and r["people_linked"] == 2
    after = c.ok("get", f"/api/persons/{oscar}/overview")
    assert next(i for i in after["items"] if i["id"] == "census-1920")["status"] == "found"     # the checklist knows
    assert "Harold Lindqvist" in [k["name"] for k in after["family"]["children"]]
    src = c.ok("get", f"/api/sources/{r['source_id']}")
    assert src["transcription"].startswith("1920 United States Federal Census") and src["url"] == "https://www.ancestry.com/x"


def test_clip_endpoint_parks_the_page_and_suggests_who_it_is_about(make_client):
    c = make_client()
    pid, oscar, *_ = _family(c)
    r = c.c.post("/clip", data={"text": FAMILYSEARCH, "url": "https://www.familysearch.org/ark:/61903/1:1:X", "title": "United States Census, 1920"},
                 follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/#/clip/")
    cid = r.headers["location"].rsplit("/", 1)[1]
    clip = c.ok("get", f"/api/clips/{cid}")
    assert clip["url"].startswith("https://www.familysearch.org")
    who = c.ok("post", f"/api/projects/{pid}/capture/who", json={"text": clip["text"], "url": clip["url"], "title": clip["title"]})
    assert [x["id"] for x in who["candidates"]] == [oscar]
