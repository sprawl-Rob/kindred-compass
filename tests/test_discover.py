"""Searching all sources for a name (not tied to a person), and turning results into people in the tree."""
from urllib.parse import parse_qs, urlsplit

from app.integrations import ADAPTERS

from tests.test_research import FakeArchive, wait


def test_links_cover_member_societies_with_prefilled_or_copyable_searches(make_client):
    c = make_client()
    pid = c.ok("post", "/api/projects", json={"name": "S"})["id"]
    r = c.ok("get", f"/api/projects/{pid}/discover/links", params={"given": "John", "surname": "Petrie", "year_from": 1840, "year_to": 1880,
                                                                   "place": "Frankfort, Herkimer, New York"})
    by = {l["seed_key"]: l for l in r["links"]}
    aa = by["american-ancestors"]
    q = parse_qs(urlsplit(aa["url"]).query)
    assert aa["prefilled"] and q["lastname"] == ["Petrie"] and q["fromyear"] == ["1840"] and q["location"] == ["Frankfort, New York"]
    assert by["nygb-online-records"]["copy"] == "John Petrie — Location: Herkimer County" and not by["nygb-online-records"]["prefilled"]
    assert by["hchs-library"]["coverage"] == "match"
    # marking a membership puts the source first
    c.ok("put", "/api/settings/research-prefs", json={"subscriptions": [by["nygb-online-records"]["provider_id"]]})
    r = c.ok("get", f"/api/projects/{pid}/discover/links", params={"surname": "Petrie", "place": "Herkimer County, New York"})
    assert r["links"][0]["seed_key"] == "nygb-online-records" and r["links"][0]["mine"]


def test_search_run_finds_new_people_who_can_be_added_or_attached(make_client, monkeypatch):
    monkeypatch.setitem(ADAPTERS, "fake_news", FakeArchive)
    FakeArchive.calls = []
    c = make_client()
    pid = c.ok("post", "/api/projects", json={"name": "S"})["id"]
    kid = c.ok("post", f"/api/projects/{pid}/persons", json={"names": [{"given": "Mary", "surname": "Ferris"}], "living_status": "deceased"})
    q = {"given": "Josiah", "surname": "Ferris", "year_from": 1850, "year_to": 1905, "place": "Fitchburg, Massachusetts"}
    plan = c.ok("post", f"/api/projects/{pid}/discover/plan", json={"query": q, "options": {"adapters": ["fake_news"]}})
    assert plan["queries"] and plan["queries"][0]["query"]["text"] == "Josiah Ferris" and plan["queries"][0]["query"]["state"] == "Massachusetts"
    run = c.ok("post", f"/api/projects/{pid}/discover/runs", json={"query": q, "options": {"adapters": ["fake_news"]}})
    run = wait(c, run["id"])
    assert run["person_id"] is None and run["status"] == "completed"
    hit = next(h for h in run["hits"] if h["strength"] != "weak")
    assert hit["person_id"] is None and any("josiah ferris" in r.lower() for r in hit["reasons"])
    # unassigned finds wait in Leads
    assert any(h["id"] == hit["id"] for h in c.ok("get", f"/api/projects/{pid}/research/review"))
    p = c.ok("post", f"/api/research/hits/{hit['id']}/new-person", json={"given": "Josiah", "surname": "Ferris", "sex": "M", "fact_type": "death",
                                                                          "date_text": "1903", "place": "Fitchburg, Massachusetts",
                                                                          "related_person_id": kid["id"], "relationship": "parent"})
    o = c.ok("get", f"/api/persons/{kid['id']}/overview")
    assert o["family"]["parents"][0]["name"] == "Josiah Ferris"
    newp = c.ok("get", f"/api/persons/{p['id']}")
    assert any(cl["claim_type"] == "death" and cl["date_text"] == "1903" for cl in newp["claims"])
    assert any(s["origin"] == "research" for s in c.ok("get", f"/api/projects/{pid}/sources"))
    # another result attached to an existing person instead
    other = next((h for h in run["hits"] if h["id"] != hit["id"]), None)
    if other:
        r = c.ok("post", f"/api/research/hits/{other['id']}/assign", json={"person_id": kid["id"]})
        assert r["person_id"] == kid["id"] and r["status"] == "saved"
