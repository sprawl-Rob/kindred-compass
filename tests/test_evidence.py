"""Claims, sources, citations; supporting and contradicting evidence; conflicts kept; duplicates."""
from app.dates import parse_date


def person_with_two_births(client, pid):
    p = client.ok("post", f"/api/projects/{pid}/persons", json={
        "names": [{"given": "Josiah", "surname": "Whitcomb"}], "living_status": "deceased",
        "claims": [{"claim_type": "birth", "date_text": "abt 1852", "place": {"country": "United States", "region": "Massachusetts"}}]})
    second = client.ok("post", f"/api/projects/{pid}/claims", json={
        "person_id": p["id"], "claim_type": "birth", "date_text": "1849", "place": {"country": "United States", "region": "New Hampshire"}})
    return p, second


def test_conflicting_claims_are_both_kept_and_flagged(client, project):
    pid = project["id"]
    p, second = person_with_two_births(client, pid)
    full = client.ok("get", f"/api/persons/{p['id']}")
    births = [c for c in full["claims"] if c["claim_type"] == "birth"]
    assert len(births) == 2
    assert {b["date_text"] for b in births} == {"abt 1852", "1849"}
    assert full["conflicts"] and full["conflicts"][0]["claim_type"] == "birth"
    assert "dates differ" in full["conflicts"][0]["reason"]


def test_source_citation_and_support_contradict(client, project):
    pid = project["id"]
    p, second = person_with_two_births(client, pid)
    first = next(c for c in client.ok("get", f"/api/persons/{p['id']}")["claims"] if c["date_text"] == "abt 1852")
    src = client.ok("post", f"/api/projects/{pid}/sources", json={
        "title": "Death register entry", "repository": "Town clerk", "page_ref": "Entry 77", "record_date_text": "1903",
        "record_format": "original_image", "informant": "Son", "informant_knowledge": "secondary",
        "transcription": "born New Hampshire", "url": "https://example.org/record/77", "accessed_on": "2026-10-01"})
    assert "Death register entry" in src["citation_text"] and "Entry 77" in src["citation_text"] and "accessed 2026-10-01" in src["citation_text"]
    client.ok("post", f"/api/claims/{second['id']}/evidence", json={"source_id": src["id"], "stance": "supports", "identity_match": "probable", "assessment": "weak"})
    client.ok("post", f"/api/claims/{first['id']}/evidence", json={"source_id": src["id"], "stance": "contradicts", "identity_match": "probable"})
    full = client.ok("get", f"/api/persons/{p['id']}")
    c1 = next(c for c in full["claims"] if c["id"] == first["id"])
    c2 = next(c for c in full["claims"] if c["id"] == second["id"])
    assert c1["evidence_summary"]["contradicts"] == 1 and c2["evidence_summary"]["supports"] == 1
    # Linking evidence never changes either claim's dates or status
    assert c1["date_text"] == "abt 1852" and c2["date_text"] == "1849"
    s = client.ok("get", f"/api/sources/{src['id']}")
    assert {c["stance"] for c in s["claims"]} == {"supports", "contradicts"}


def test_cannot_confirm_without_support_and_tree_is_not_proof(client, project):
    pid = project["id"]
    a = client.ok("post", f"/api/projects/{pid}/persons", json={"display_name": "Child"})
    b = client.ok("post", f"/api/projects/{pid}/persons", json={"display_name": "Parent"})
    rel = client.ok("post", f"/api/projects/{pid}/claims", json={"person_id": a["id"], "claim_type": "relationship",
                                                                   "relationship_type": "child", "related_person_id": b["id"]})
    assert rel["status"] == "tentative"
    r = client.patch(f"/api/claims/{rel['id']}", json={"status": "confirmed"})
    assert r.status_code == 422
    tree = client.ok("post", f"/api/projects/{pid}/sources", json={"title": "Online tree", "record_format": "contributed_tree"})
    client.ok("post", f"/api/claims/{rel['id']}/evidence", json={"source_id": tree["id"], "stance": "supports"})
    r = client.patch(f"/api/claims/{rel['id']}", json={"status": "confirmed"})
    assert r.status_code == 422 and "clues, not proof" in r.json()["detail"]
    claim = client.ok("get", f"/api/persons/{a['id']}")["claims"][0]
    assert claim["evidence_summary"]["supports_only_clue_formats"]
    # With an explicit reasoning note the researcher can still decide
    ok = client.ok("patch", f"/api/claims/{rel['id']}", json={"status": "confirmed", "status_note": "Corroborated by family Bible held privately"})
    assert ok["status"] == "confirmed"


def test_new_claim_cannot_start_confirmed(client, project):
    p = client.ok("post", f"/api/projects/{project['id']}/persons", json={"display_name": "X"})
    r = client.post(f"/api/projects/{project['id']}/claims", json={"person_id": p["id"], "claim_type": "birth", "status": "confirmed"})
    assert r.status_code == 422


def test_duplicate_source_detection_preserves_provenance(client, project):
    pid = project["id"]
    a = client.ok("post", f"/api/projects/{pid}/sources", json={"title": "1880 census", "url": "https://www.example.org/rec/1/", "provenance_note": "found via site A"})
    r = client.post(f"/api/projects/{pid}/sources", json={"title": "Census 1880 copy", "url": "https://example.org/rec/1", "provenance_note": "found via site B"})
    assert r.status_code == 409 and r.json()["matches"][0]["id"] == a["id"]
    b = client.ok("post", f"/api/projects/{pid}/sources", json={"title": "Census 1880 copy", "url": "https://example.org/rec/1",
                                                               "provenance_note": "found via site B", "duplicate_of_id": a["id"]})
    assert b["duplicate_of_id"] == a["id"] and b["provenance_note"] == "found via site B"
    assert client.ok("get", f"/api/sources/{a['id']}")["provenance_note"] == "found via site A"
    assert len(client.ok("get", f"/api/projects/{pid}/sources")) == 2


def test_tentative_relationships_never_merge_people(client, project):
    pid = project["id"]
    a = client.ok("post", f"/api/projects/{pid}/persons", json={"display_name": "John Smith"})
    b = client.ok("post", f"/api/projects/{pid}/persons", json={"display_name": "John Smith"})
    assert a["id"] != b["id"]
    assert len(client.ok("get", f"/api/projects/{pid}/persons")) == 2


def test_parse_dates():
    assert parse_date("abt 1852") == {"date_qualifier": "about", "year_from": 1850, "year_to": 1854}
    assert parse_date("bef 1880") == {"date_qualifier": "before", "year_from": 1860, "year_to": 1879}
    assert parse_date("bef Mar 1880")["year_to"] == 1880
    assert parse_date("bet 1870 and 1875") == {"date_qualifier": "between", "year_from": 1870, "year_to": 1875}
    assert parse_date("1850s") == {"date_qualifier": "about", "year_from": 1850, "year_to": 1859}
    assert parse_date("12 Mar 1861") == {"date_qualifier": "exact", "year_from": 1861, "year_to": 1861}
    assert parse_date("")["date_qualifier"] == "unknown"
