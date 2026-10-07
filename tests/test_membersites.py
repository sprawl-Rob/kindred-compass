"""Member/society sites: American Ancestors and NYG&B links, Herkimer County Historical Society holdings."""
from urllib.parse import parse_qs, urlsplit

from app import membersites as ms

NY = {"country": "United States", "region": "New York", "county": "Herikmer", "municipality": "Frankfort"}   # misspelt as in real trees


def test_ny_county_names_are_corrected():
    assert ms.ny_county("Herikmer") == "Herkimer" and ms.ny_county("Herkimer County") == "Herkimer"
    assert ms.ny_county("Worcester") is None


def test_checklist_gets_member_links_and_herkimer_library(make_client):
    c = make_client()
    pid = c.ok("post", "/api/projects", json={"name": "NY"})["id"]
    person = c.ok("post", f"/api/projects/{pid}/persons", json={
        "names": [{"given": "Ann", "surname": "Petrie"}], "sex": "F", "living_status": "deceased",
        "claims": [{"claim_type": "birth", "date_text": "1820", "place": NY}, {"claim_type": "residence", "date_text": "1850", "place": NY},
                   {"claim_type": "death", "date_text": "1890", "place": NY}]})
    items = {i["id"]: i for i in c.ok("get", f"/api/persons/{person['id']}/overview")["items"]}
    hk = items["herkimer-hs"]
    assert "Frankfort" in hk["why"] and "Cemetery files" in hk["tells"] and "1825" in hk["tells"]
    assert hk["searches"][0]["url"].startswith("mailto:herkimerhistoryresearch@yahoo.com?")
    assert "state-census-New York-1845" in items       # NY's early state censuses (heads of household)
    links = items["census-1850"]["searches"]
    aa = next(l for l in links if l["site"] == "American Ancestors")
    q = parse_qs(urlsplit(aa["url"]).query)
    assert q["firstname"] == ["Ann"] and q["lastname"] == ["Petrie"] and q["fromyear"] == ["1850"] and q["toyear"] == ["1850"]
    assert q["location"] == ["Frankfort, New York"] and q["searchPage"] == ["Advanced-Search"]
    ny = next(l for l in links if l["site"] == "NYG&B")
    assert ny["copy"] == "Ann Petrie — Location: Herkimer County" and ny["member"]


def test_no_member_links_outside_their_regions(make_client):
    c = make_client()
    pid = c.ok("post", "/api/projects", json={"name": "CA"})["id"]
    person = c.ok("post", f"/api/projects/{pid}/persons", json={
        "names": [{"given": "Juan", "surname": "Ortega"}], "sex": "M", "living_status": "deceased",
        "claims": [{"claim_type": "birth", "date_text": "1880", "place": {"country": "United States", "region": "California", "municipality": "Anaheim"}}]})
    items = c.ok("get", f"/api/persons/{person['id']}/overview")["items"]
    assert not any(l.get("member") for i in items for l in i.get("searches", [])) and not any(i["id"] == "herkimer-hs" for i in items)
