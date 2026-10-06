"""Combining two trees: match suggestions (incl. conflicting dates), joining people, no duplicate facts, undo."""

US = {"country": "United States", "region": "Massachusetts", "county": "Worcester", "municipality": "Fitchburg"}


def _person(c, pid, given, surname, sex, claims=()):
    return c.ok("post", f"/api/projects/{pid}/persons", json={"names": [{"given": given, "surname": surname}], "sex": sex,
                                                              "living_status": "deceased", "claims": list(claims)})["id"]


def _rel(c, pid, a, kind, b):
    c.ok("post", f"/api/projects/{pid}/claims", json={"person_id": a, "claim_type": "relationship", "relationship_type": kind, "related_person_id": b})


def _trees(c):
    # Father's side: Paul, his wife Ann, and Ann's father "Leon" known only by name
    dad = c.ok("post", "/api/projects", json={"name": "Dad's tree"})["id"]
    paul = _person(c, dad, "Paul", "Hartley", "M", [{"claim_type": "birth", "date_text": "1933", "place": US}])
    ann = _person(c, dad, "Ann", "Brodeur", "F")
    leon_d = _person(c, dad, "Leon", "Brodeur", "M")
    _rel(c, dad, paul, "spouse", ann)
    _rel(c, dad, ann, "child", leon_d)
    # Mother's side: Leon with dates, his parents, and his father Georges with a typo'd birth year
    mom = c.ok("post", "/api/projects", json={"name": "Mom's tree"})["id"]
    leon = _person(c, mom, "Leon", "Brodeur", "M", [{"claim_type": "birth", "date_text": "19 Nov 1917", "place": US},
                                                    {"claim_type": "death", "date_text": "1996", "place": US}])
    albert = _person(c, mom, "Albert", "Brodeur", "M", [{"claim_type": "birth", "date_text": "1884", "place": {"country": "Canada", "region": "Quebec"}}])
    vit = _person(c, mom, "Vitaline", "Brodeur", "F", [{"claim_type": "birth", "date_text": "1881"}])
    _rel(c, mom, leon, "child", albert)
    _rel(c, mom, leon, "child", vit)
    _rel(c, mom, albert, "spouse", vit)
    return dad, mom, {"paul": paul, "ann": ann, "leon_d": leon_d, "leon": leon, "albert": albert}


def test_suggest_and_combine_connects_the_families_and_can_be_undone(make_client):
    c = make_client()
    dad, mom, ids = _trees(c)
    sg = c.ok("get", f"/api/projects/{dad}/combine/suggest?source={mom}")
    assert [(p["source"]["name"], p["target"]["name"]) for p in sg["pairs"]] == [("Leon Brodeur", "Leon Brodeur")]
    assert sg["pairs"][0]["level"] == "possible" and not sg["pairs"][0]["recommended"]   # a name alone needs the user's confirmation
    run = c.ok("post", f"/api/projects/{dad}/combine", json={"source_project_id": mom, "pairs": [{"source": ids["leon"], "target": ids["leon_d"]}]})
    assert run["stats"]["people_added"] == 2 and run["stats"]["people_merged"] == 1
    # Ann's father now has his dates and his own parents: the two sides are connected
    t = c.ok("get", f"/api/projects/{dad}/tree?root={ids['ann']}&depth=3")
    leon_node = t["pedigree"]["parents"][0]
    assert leon_node["name"] == "Leon Brodeur" and leon_node["lifespan"] == "1917–1996"
    assert {p["name"] for p in leon_node["parents"]} == {"Albert Brodeur", "Vitaline Brodeur"}
    assert len(c.ok("get", f"/api/projects/{mom}/persons")) == 3                       # the source tree is untouched
    c.ok("post", f"/api/combine/{run['id']}/undo")
    assert len(c.ok("get", f"/api/projects/{dad}/persons")) == 3
    t = c.ok("get", f"/api/projects/{dad}/tree?root={ids['ann']}&depth=3")
    assert t["pedigree"]["parents"][0]["lifespan"] in ("", None)


def test_conflicting_dates_with_matching_family_are_flagged_not_hidden(make_client):
    c = make_client()
    a = c.ok("post", "/api/projects", json={"name": "A"})["id"]
    b = c.ok("post", "/api/projects", json={"name": "B"})["id"]
    for pid, year in ((a, "1883"), (b, "1833")):
        g = _person(c, pid, "George", "Pelland", "M", [{"claim_type": "birth", "date_text": year}])
        kid = _person(c, pid, "Noella", "Pelland", "F", [{"claim_type": "birth", "date_text": "1918", "place": US}])
        _rel(c, pid, kid, "child", g)
    sg = c.ok("get", f"/api/projects/{a}/combine/suggest?source={b}")
    lv = {p["source"]["name"]: p["level"] for p in sg["pairs"]}
    assert lv["Noella Pelland"] == "high" and lv["George Pelland"] == "conflict"
    george = next(p for p in sg["pairs"] if p["source"]["name"] == "George Pelland")
    assert any("differ" in r for r in george["reasons"]) and not george["recommended"]


def test_pairs_must_belong_to_the_trees(make_client):
    c = make_client()
    dad, mom, ids = _trees(c)
    r = c.post(f"/api/projects/{dad}/combine", json={"source_project_id": mom, "pairs": [{"source": ids["paul"], "target": ids["leon"]}]})
    assert r.status_code == 422 and "belong" in r.text
