"""End-to-end research workflow (the 11 acceptance steps), through the HTTP API."""
import json

from app.integrations import build_search_link
from app.integrations.loc import ChroniclingAmericaAdapter


def test_full_research_workflow(make_client):
    c = make_client()
    pid = c.ok("post", "/api/projects", json={"name": "Whitcomb research"})["id"]

    # 1. Person with an approximate date and a location
    person = c.ok("post", f"/api/projects/{pid}/persons", json={
        "names": [{"name_type": "birth", "given": "Josiah", "surname": "Whitcomb"}], "living_status": "deceased",
        "claims": [{"claim_type": "birth", "date_text": "abt 1852",
                    "place": {"country": "United States", "region": "Massachusetts", "county": "Worcester", "municipality": "Fitchburg"}}]})
    birth = person["claims"][0]
    assert birth["date_qualifier"] == "about" and (birth["year_from"], birth["year_to"]) == (1850, 1854)

    # 2. Research question
    q = c.ok("post", f"/api/projects/{pid}/questions", json={"person_id": person["id"], "question": "Who were Josiah's parents?",
                                                            "question_type": "identify_parents"})

    # 3. Discover relevant resources and collections
    found = c.ok("post", "/api/directory/search", json={"country": "United States", "region": "Massachusetts", "county": "Worcester"})
    assert found["total"] > 5
    recs = c.ok("post", f"/api/projects/{pid}/recommendations", json={"question_id": q["id"]})
    assert len(recs["recommendations"]) >= 5

    # 4. Understand why each recommended source is useful
    for r in recs["recommendations"]:
        assert r["why"] and r["coverage_sentence"] and r["next_action"]["label"] and r["question_it_may_answer"]

    # 5. Open a provider search or copy a suggested query
    fs = next(r for r in recs["recommendations"] + recs["already_searched"] if r["collection"]["name"].startswith("FamilySearch Historical"))
    link = c.ok("post", f"/api/directory/collections/{fs['collection']['id']}/search-link",
                json={"given": "Josiah", "surname": "Whitcomb", "year_from": 1850, "year_to": 1854})
    assert link["prefilled"] and "q.surname=Whitcomb" in link["url"] and link["url"].startswith("https://www.familysearch.org/")
    assert "Josiah Whitcomb" in fs["suggested_query"]["text"]
    unverified = next(r for r in recs["recommendations"] if not r["collection"]["search_link_verified"])
    l2 = c.ok("post", f"/api/directory/collections/{unverified['collection']['id']}/search-link", json={"surname": "Whitcomb"})
    assert not l2["prefilled"] and "copy the suggested query" in l2["note"]

    # 6. Log a search with no result
    entry = c.ok("post", f"/api/projects/{pid}/log", json={
        "person_id": person["id"], "question_id": q["id"], "collection_id": fs["collection"]["id"],
        "query_text": "Josiah Whitcomb b. 1850-1854 Massachusetts", "name_variants": ["Josiah Whitcomb"], "filters_text": "birthplace Massachusetts",
        "year_from": 1850, "year_to": 1854, "place_text": "Massachusetts", "outcome": "no_result", "coverage_notes": "Index only"})
    assert entry["outcome"] == "no_result"

    # 7. Receive an appropriate alternative research step
    kinds = {a["kind"] for a in entry["alternatives"]}
    assert {"spelling", "full_text"} <= kinds
    recs2 = c.ok("post", f"/api/projects/{pid}/recommendations", json={"question_id": q["id"]})
    assert any(r["collection"]["id"] == fs["collection"]["id"] for r in recs2["already_searched"])

    # 8. Save evidence and a citation against a claim
    src = c.ok("post", f"/api/projects/{pid}/sources", json={
        "title": "1880 census, Fitchburg, Josiah Whitcombe household", "repository": "National Archives", "page_ref": "ED 123, sheet 12",
        "record_date_text": "1880", "record_format": "original_image", "informant_knowledge": "undetermined",
        "transcription": "Whitcombe, Josiah, 28, b. Mass.", "url": "https://example.org/census/1880/123", "accessed_on": "2026-10-05",
        "link_claim_id": birth["id"], "link": {"stance": "supports", "identity_match": "probable", "assessment": "moderate"}})
    assert "ED 123" in src["citation_text"] and src["claims"][0]["stance"] == "supports"

    # 9. Preserve a conflicting claim without overwriting either
    other = c.ok("post", f"/api/projects/{pid}/claims", json={"person_id": person["id"], "claim_type": "birth", "date_text": "1849",
                                                             "place": {"country": "United States", "region": "New Hampshire"}})
    p_full = c.ok("get", f"/api/persons/{person['id']}")
    births = {x["id"]: x for x in p_full["claims"] if x["claim_type"] == "birth"}
    assert set(births) == {birth["id"], other["id"]}
    assert births[birth["id"]]["date_text"] == "abt 1852" and births[other["id"]]["date_text"] == "1849"
    assert p_full["conflicts"]

    # 10. Restart the application and recover the work
    c2 = make_client()
    p_again = c2.ok("get", f"/api/persons/{person['id']}")
    assert len([x for x in p_again["claims"] if x["claim_type"] == "birth"]) == 2
    assert c2.ok("get", f"/api/projects/{pid}/log")[0]["outcome"] == "no_result"
    assert c2.ok("get", f"/api/sources/{src['id']}")["citation_text"] == src["citation_text"]

    # 11. Export and restore the research project
    doc = c2.ok("get", f"/api/projects/{pid}/export.json")
    backup = c2.ok("post", "/api/backups")
    c2.ok("delete", f"/api/projects/{pid}")
    assert all(p["id"] != pid for p in c2.ok("get", "/api/projects"))
    r = c2.c.post("/api/import/project", headers={"X-Kindred": "1"}, files={"file": ("p.json", json.dumps(doc).encode(), "application/json")})
    new_pid = r.json()["project_id"]
    restored_people = c2.ok("get", f"/api/projects/{new_pid}/persons")
    assert restored_people[0]["display_name"] == "Josiah Whitcomb"
    assert c2.ok("get", f"/api/projects/{new_pid}/log")[0]["outcome"] == "no_result"
    # ...and a full backup restore brings back the original ids too
    rr = c2.c.post("/api/backups/restore", headers={"X-Kindred": "1"}, data={"name": backup["name"], "confirm": "RESTORE"})
    assert rr.status_code == 200
    assert c2.ok("get", f"/api/persons/{person['id']}")["display_name"] == "Josiah Whitcomb"


def test_demo_project_is_separate_and_labelled(make_client):
    c = make_client(load_demo=True)
    projects = c.ok("get", "/api/projects")
    demo = [p for p in projects if p["is_demo"]]
    assert len(demo) == 1 and "fictional" in demo[0]["name"].lower()
    srcs = c.ok("get", f"/api/projects/{demo[0]['id']}/sources")
    assert all("FICTIONAL" in (s["title"] + (s["provenance_note"] or "")) for s in srcs)
    assert all(not s["url"] for s in srcs)  # no links to real records
    # deleting the demo does not recreate it on restart
    c.ok("delete", f"/api/projects/{demo[0]['id']}")
    c2 = make_client(load_demo=True)  # real restart on the same data dir
    assert not [p for p in c2.ok("get", "/api/projects") if p["is_demo"]]


def test_loc_adapter_maps_documented_parameters():
    seen = {}

    def fake_get(url, params):
        seen.update(params)
        return {"results": [{"title": "Image 2 of The Republican", "date": "1894-02-22", "url": "https://www.loc.gov/resource/x/?sp=2",
                             "partof_title": ["the republican"], "location_city": ["oakland"], "location_state": ["maryland"],
                             "description": "… Mrs Whitcomb Followed Her Husband …"}],
                "pagination": {"of": 680, "current": 1}}
    out = ChroniclingAmericaAdapter(http_get=fake_get).search_simple({"q": "Whitcomb", "year_from": 1880, "year_to": 1900, "state": "Massachusetts"})
    assert seen["q"] == "Whitcomb" and seen["fo"] == "json" and seen["dates"] == "1880/1900" and seen["fa"] == "location_state:massachusetts"
    assert out["total"] == 680 and out["items"][0]["location"] == "oakland, maryland" and "OCR" in out["items"][0]["ocr_note"]


def test_search_link_builder_only_fills_verified_templates():
    c = {"search_url": "https://example.org/search", "search_url_template": "https://example.org/s?q={q}&from={year_from}", "search_link_verified": False}
    assert build_search_link(c, {"q": "x"}) == {"url": "https://example.org/search", "prefilled": False, "note": build_search_link(c, {})["note"]}
    c["search_link_verified"] = True
    out = build_search_link(c, {"given": "Ann", "surname": "Lee"})
    assert out["prefilled"] and out["url"] == "https://example.org/s?q=Ann+Lee"  # empty year param dropped
    c["search_url_template"] = "https://example.org/s?q={q}&x={unknown}"
    assert not build_search_link(c, {"q": "x"})["prefilled"]
