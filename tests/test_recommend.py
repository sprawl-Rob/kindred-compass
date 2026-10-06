"""Deterministic recommendation explanations; negative-search history and alternatives."""
from app import names as nm


def setup_person(client, pid, **extra):
    person = client.ok("post", f"/api/projects/{pid}/persons", json={
        "names": [{"given": "Josiah", "surname": "Whitcomb"}], "living_status": "deceased",
        "claims": [{"claim_type": "birth", "date_text": "abt 1852",
                    "place": {"country": "United States", "region": "Massachusetts", "county": "Worcester"}}], **extra})
    q = client.ok("post", f"/api/projects/{pid}/questions", json={"person_id": person["id"], "question": "Who were his parents?",
                                                                  "question_type": "identify_parents"})
    return person, q


def rec(client, pid, **body):
    return client.ok("post", f"/api/projects/{pid}/recommendations", json=body)


def test_recommendations_are_deterministic_and_explained(client, project):
    pid = project["id"]
    person, q = setup_person(client, pid)
    a = rec(client, pid, question_id=q["id"])
    b = rec(client, pid, question_id=q["id"])
    assert [r["collection"]["id"] for r in a["recommendations"]] == [r["collection"]["id"] for r in b["recommendations"]]
    assert a["recommendations"], "expected suggestions"
    for r in a["recommendations"]:
        for key in ("why", "question_it_may_answer", "coverage", "access", "search_methods", "suggested_query", "next_action", "uncertainty", "headline"):
            assert key in r
        assert r["why"] and r["next_action"]["label"]
        assert r["access"]["search"] and r["access"]["images"] and r["access"]["copies"]
    assert "not the probability" in a["score_note"]
    # A Worcester County probate repository should be suggested for a parents question in Worcester County.
    top_names = [r["collection"]["name"] for r in a["recommendations"][:6]]
    assert "Worcester Probate and Family Court" in top_names
    w = next(r for r in a["recommendations"] if r["collection"]["name"] == "Worcester Probate and Family Court")
    assert any("Local repository" in x for x in w["why"])
    assert any("probate" in x.lower() for x in w["why"])
    assert "Josiah Whitcomb" in w["suggested_query"]["text"]


def test_coverage_sentence_mentions_browse_only(client, project):
    pid = project["id"]
    person = client.ok("post", f"/api/projects/{pid}/persons", json={
        "names": [{"given": "Anna", "surname": "Huber"}], "living_status": "deceased",
        "claims": [{"claim_type": "baptism", "date_text": "1810", "place": {"country": "Austria"}}]})
    q = client.ok("post", f"/api/projects/{pid}/questions", json={"person_id": person["id"], "question": "Baptism?", "question_type": "find_birth"})
    r = rec(client, pid, question_id=q["id"])
    m = next(x for x in r["recommendations"] if x["collection"]["name"].startswith("Matricula"))
    assert "browsing images" in m["coverage_sentence"]
    assert m["next_action"]["kind"] == "browse"


def test_unrelated_place_is_not_recommended(client, project):
    pid = project["id"]
    person, q = setup_person(client, pid)
    r = rec(client, pid, question_id=q["id"])
    names = {x["collection"]["name"] for x in r["recommendations"]}
    assert "ScotlandsPeople" not in names
    assert "BLM General Land Office Records" not in names  # Massachusetts is not a Public Land State


def test_negative_search_moves_collection_and_suggests_alternatives(client, project):
    pid = project["id"]
    person, q = setup_person(client, pid)
    before = rec(client, pid, question_id=q["id"])
    fs_id = next(c["id"] for g in client.ok("post", "/api/directory/search", json={"q": "FamilySearch Historical"})["groups"].values()
                 for c in g if c["name"].startswith("FamilySearch Historical Records"))
    entry = client.ok("post", f"/api/projects/{pid}/log", json={
        "person_id": person["id"], "question_id": q["id"], "collection_id": fs_id, "query_text": "Josiah Whitcomb",
        "name_variants": ["Josiah Whitcomb"], "year_from": 1850, "year_to": 1854, "outcome": "no_result"})
    kinds = {a["kind"] for a in entry["alternatives"]}
    assert {"spelling", "dates", "full_text", "local"} <= kinds
    for a in entry["alternatives"]:
        assert a["reason"] and a["title"]
    spelling = next(a for a in entry["alternatives"] if a["kind"] == "spelling")
    assert "Whitcomb" not in spelling["variants"]  # already tried
    after = rec(client, pid, question_id=q["id"])
    assert fs_id not in [r["collection"]["id"] for r in after["recommendations"]]
    already = [r for r in after["already_searched"] if r["collection"]["id"] == fs_id]
    assert already and "does not mean the record does not exist" in already[0]["history_note"]
    assert after["alternatives"] and after["alternatives"][0]["outcome"] == "no_result"


def test_search_status_distinguishes_states(client, project):
    pid = project["id"]
    person, q = setup_person(client, pid)
    cid = client.ok("post", "/api/directory/search", json={"q": "FreeBMD"})["groups"]
    cid = next(c["id"] for g in cid.values() for c in g)
    from app.research_log import search_status
    log = []
    assert search_status(log, cid)["state"] == "not_searched"
    log = [{"collection_id": cid, "outcome": "no_result", "searched_on": "2026-01-01"}]
    assert search_status(log, cid)["state"] == "searched_no_result"
    log = [{"collection_id": cid, "outcome": "records_unavailable", "searched_on": "2026-01-01"}]
    assert search_status(log, cid)["state"] == "records_unavailable"


def test_access_preferences_hide_but_keep(client, project):
    pid = project["id"]
    person, q = setup_person(client, pid)
    r = rec(client, pid, question_id=q["id"], prefs={"access": "free"})
    assert r["hidden_by_preferences"], "subscription sources should be reported as hidden, not dropped"
    assert all(h["hidden_reason"] for h in r["hidden_by_preferences"])


def test_works_with_minimal_information(client, project):
    pid = project["id"]
    p = client.ok("post", f"/api/projects/{pid}/persons", json={"display_name": "Unknown Smith"})
    r = rec(client, pid, person_id=p["id"])
    assert r["warnings"]  # explains that place/dates would help
    assert isinstance(r["recommendations"], list)


def test_name_variants_never_infer_origin():
    out = nm.suggest_for_person({"names": [{"given": "Mary", "surname": "McCarthy"}]})
    reasons = " ".join(g["reason"] for g in out["groups"]).lower()
    for word in ("irish", "jewish", "german", "ethnic", "origin"):
        assert word not in reasons
    assert nm.soundex("Whitcomb") == "W325"
    assert nm.soundex("Tymczak") == "T522"
