"""GEDCOM / Ancestry import: parsing, preview, commit, media, repeat imports, review, undo, safety."""
import json

import pytest

from app.gedcom.gdates import parse_gedcom_date
from app.gedcom.media import match_reference, safe_relpath
from app.gedcom.parser import parse_bytes
from tests import gedcom_fixtures as fx

H = {"X-Kindred": "1"}


def upload(client, name, data, media=None, lineage_id=None, media_paths=None):
    files = [("gedcom", (name, data, "application/octet-stream"))]
    form = {}
    for rel, content in (media or {}).items():
        files.append(("media", (rel.split("/")[-1], content, "application/octet-stream")))
    if media:
        form["media_path"] = list((media or {}).keys()) if media_paths is None else media_paths
    if lineage_id:
        form["lineage_id"] = lineage_id
    r = client.c.post("/api/imports", headers=H, files=files, data=form)
    return r


def staged(client, *a, **k):
    r = upload(client, *a, **k)
    assert r.status_code == 200, r.text
    return r.json()


def commit(client, bid):
    r = client.c.post(f"/api/imports/{bid}/commit", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def persons_by_name(client, pid):
    return {p["display_name"]: p for p in client.ok("get", f"/api/projects/{pid}/persons")}


# ------------------------------------------------------------------ parsing units

def test_gedcom_dates_preserve_uncertainty():
    assert parse_gedcom_date("ABT 1852")["date_qualifier"] == "about"
    assert parse_gedcom_date("CAL 1860")["date_qualifier"] == "calculated"
    assert parse_gedcom_date("EST 1700")["date_qualifier"] == "estimated"
    d = parse_gedcom_date("BET 1853 AND 1856")
    assert (d["date_qualifier"], d["year_from"], d["year_to"]) == ("between", 1853, 1856)
    d = parse_gedcom_date("FROM 1864 TO 1865")
    assert (d["year_from"], d["year_to"]) == (1864, 1865)
    d = parse_gedcom_date("1750/51")
    assert (d["year_from"], d["year_to"]) == (1750, 1751)
    d = parse_gedcom_date("INT 1890 (about the time of the flood)")
    assert d["phrase"] == "about the time of the flood" and d["year_from"] == 1890
    d = parse_gedcom_date("@#DJULIAN@ 1 MAR 1700")
    assert d["calendar"] == "Julian" and d["note"]
    assert parse_gedcom_date("(unknown)")["date_qualifier"] == "unknown"


def test_ansel_crlf_and_version_detection():
    g = parse_bytes(fx.ROOTSMAGIC_ANSEL)
    assert g.version == "5.5.1" and g.declared_charset == "ANSEL" and g.encoding == "ansel"
    names = [r.first("NAME").value for r in g.records if r.tag == "INDI"]
    assert "José /García/" in names and "María /López/" in names


def test_utf16_and_mislabelled_utf8():
    g = parse_bytes(fx.FTM.replace("CHAR UTF-8", "CHAR UNICODE").encode("utf-16"))
    assert g.encoding == "utf-16" and len(g.records) > 3
    g = parse_bytes(fx.ANCESTRY_V1.replace("CHAR UTF-8", "CHAR ANSEL").encode("utf-8"))
    assert g.encoding == "utf-8" and any("valid UTF-8" in w for w in g.warnings)


def test_parse_failures_are_reported_not_dropped():
    g = parse_bytes(fx.BROKEN.encode())
    reasons = [f["reason"] for f in g.failures]
    assert any("no level number" in r for r in reasons)
    assert any("Level jumps" in r for r in reasons)
    assert any("TRLR" in w for w in g.warnings)


def test_media_matching_rules():
    files = ["Ferris Media/henry.jpg", "Other Folder/portrait.jpg", "Ferris Media/portrait.jpg"]
    m = match_reference(r"C:\Users\Rob\Documents\Family Tree Maker\Ferris Media\henry.jpg", files)
    assert m["status"] == "matched" and m["path"] == "Ferris Media/henry.jpg"
    assert match_reference("portrait.jpg", files)["status"] == "ambiguous"
    assert match_reference("https://www.ancestry.com/x.jpg", files)["status"] == "remote_not_fetched"
    assert match_reference("nothere.jpg", files)["status"] == "missing"
    assert safe_relpath("../x") is None and safe_relpath("/etc/x") is None and safe_relpath("C:/x") is None


# ------------------------------------------------------------------ preview

def test_ancestry_preview_counts_warnings_and_profiles(client):
    b = staged(client, "Ferris Family Tree.ged", fx.ANCESTRY_V1.encode())
    assert b["status"] == "previewed"
    p = b["plan"]
    d = p["detection"]
    assert d["product"] == "ancestry" and d["tree_name"].startswith("Ferris Family Tree") and d["gedcom_version"] == "5.5.1"
    c = p["counts"]
    assert c["people"] == 6 and c["families"] == 2 and c["citations"] == 1 and c["sources"] == 1 and c["repositories"] == 1
    assert c["relationships_parent_child"] == 8 and c["relationships_partner"] == 2
    assert c["media_remote_refs"] == 2 and c["media_local_refs"] == 0 and c["ancestry_record_ids"] >= 1
    assert p["relationship_qualifiers"]["adopted"] == 2 and p["relationship_qualifiers"]["step"] == 1
    assert p["relationship_qualifiers"]["not stated"] == 5   # Ancestry implies biological by leaving _FREL/_MREL out
    assert d["tree_id"] == "168300001" and d["tree_description"].startswith("Ancestors of")
    assert p["media"]["summary"] == {"not_in_export": 2}
    assert any("Stories appear" in i["how"] for i in p["media"]["items"])
    paths = {u["path"] for u in p["unsupported"]}
    assert "INDI._CUSTOMTAG" in paths and "INDI._CUSTOMTAG._DETAIL" not in paths
    mapped = {v["mapping"] for v in p["vendor_tags_mapped"]}
    assert "INDI._MILT → Military service" in mapped and any("_APID" in x for x in mapped) and any("_FREL" in x for x in mapped)
    reasons = {r for x in p["profiles"] for r in x["reasons"]}
    assert "Has more than one marriage or partnership" in reasons and "Has a non-biological or unstated parent relationship" in reasons
    assert "Name contains non-ASCII characters" in reasons and "Has alternative (conflicting) facts" in reasons
    assert all(x["original_lines"] for x in p["profiles"])
    assert "snapshot" in p["snapshot_note"].lower()
    assert p["export_contents"]["not_in_export"]
    # Nothing written to research tables before commit
    assert all("Imported" not in pr["name"] for pr in client.ok("get", "/api/projects"))


def test_zip_wrapped_ancestry_export(client):
    b = staged(client, "Ferris_Family_Tree.zip", fx.ancestry_zip())
    assert b["gedcom_member"] == "Ferris Family Tree (fictional).ged" and b["plan"]["counts"]["people"] == 6
    assert b["product"] == "ancestry"


def test_archive_with_several_gedcoms_lets_you_choose(client):
    data = fx.zip_bytes({"a/old.ged": fx.FTM.encode(), "tree.ged": fx.ANCESTRY_V1.encode()})
    b = staged(client, "two.zip", data)
    assert b["gedcom_member"] == "tree.ged" and set(b["plan"]["detection"]["archive_members"]) == {"a/old.ged", "tree.ged"}
    b = client.ok("post", f"/api/imports/{b['id']}/member", json={"member": "a/old.ged"})
    assert b["plan"]["detection"]["product"] == "ftm" and b["plan"]["counts"]["people"] == 3
    assert client.post(f"/api/imports/{b['id']}/member", json={"member": "../x.ged"}).status_code == 422


def test_rejects_non_gedcom(client):
    assert upload(client, "notes.txt", b"hello").status_code == 422
    assert upload(client, "fake.ged", b"just some text\nwithout gedcom").status_code == 422
    assert upload(client, "x.zip", fx.zip_bytes({"readme.txt": b"no gedcom"})).status_code == 422


# ------------------------------------------------------------------ commit

def test_commit_into_separate_project_with_provenance(client):
    other = client.ok("post", "/api/projects", json={"name": "My existing research"})
    b = staged(client, "Ferris Family Tree.ged", fx.ANCESTRY_V1.encode())
    done = commit(client, b["id"])
    assert done["status"] == "committed" and done["created_project"] == 1
    pid = done["project_id"]
    assert pid != other["id"]
    people = persons_by_name(client, pid)
    assert {"Josiah Ferris", "Margarethe Fehrs", "Zoë Łukasiewicz", "George Ferris", "Anna Ferris", "王 秀英"} <= set(people)
    j = client.ok("get", f"/api/persons/{people['Josiah Ferris']['id']}")
    # Alternative facts preserved side by side and flagged; nothing is "confirmed"
    births = [c for c in j["claims"] if c["claim_type"] == "birth"]
    assert {c["date_text"] for c in births} == {"abt 1852", "1849"}
    assert j["conflicts"]
    assert all(c["status"] in ("working", "tentative") and c["origin"] == "import" for c in j["claims"])
    assert all("not independently verified" in (c["status_note"] or "") for c in j["claims"])
    # Original date expression kept verbatim, place split conservatively, full place kept
    b1852 = next(c for c in births if c["date_text"] == "abt 1852")
    assert b1852["date_qualifier"] == "about" and b1852["place_label"] == "Fitchburg, Worcester, Massachusetts, USA"
    assert b1852["place_county"] == "Worcester" and b1852["place_region"] == "Massachusetts"
    # Citation with Ancestry record reference preserved and linked as unreviewed evidence
    ev = b1852["evidence"][0]
    assert ev["identity_match"] == "uncertain" and ev["assessment"] == "unassessed"
    src = client.ok("get", f"/api/sources/{ev['source_id']}")
    assert "1880 United States Federal Census" in src["title"] and src["repository"] == "Ancestry.com"
    assert "1,6742::12345678" in src["citation_text"] and "1,6742::12345679" in src["citation_text"]   # both record references kept
    assert src["transcription"] == "Josiah Ferris, 28, machinist"
    assert src["url"] == "https://www.fold3.com/record/000000/fictional"    # link written in the file; none constructed
    # Custom military fact imported as generic fact; notes and cause preserved
    mil = next(c for c in j["claims"] if c["claim_type"] == "military")
    assert mil["date_text"] == "1864-1865" and (mil["year_from"], mil["year_to"]) == (1864, 1865) and "21st Massachusetts" in mil["statement"]
    assert any(c["claim_type"] == "occupation" and "Putnam" in (c["statement"] or "") for c in j["claims"])   # _EMPLOY
    death = next(c for c in j["claims"] if c["claim_type"] == "death")
    assert "Pneumonia" in death["statement"]
    assert "long line that Ancestry split mid-word" in j["notes"] and "Second line" in j["notes"]   # CONC/CONT joined
    # Multiple marriages
    marriages = [c for c in j["claims"] if c["claim_type"] == "marriage"]
    assert len(marriages) == 2
    # Side-by-side provenance
    prov = client.ok("get", f"/api/imports/provenance/person/{j['id']}")
    item = next(i for i in prov["items"] if i["entity"]["id"] == b1852["id"])
    lines = [ln[1] for ln in item["links"][0]["gedcom"][0]["raw"]]
    assert lines == ["1 BIRT"]
    assert prov["record"]["xref"] == "@I112187149801@"
    m = client.ok("get", f"/api/projects/{pid}/persons")
    marg = client.ok("get", f"/api/persons/{next(x['id'] for x in m if x['display_name'] == 'Margarethe Fehrs')}")
    assert any(c["claim_type"] == "immigration" and c["date_text"] == "1868" for c in marg["claims"])   # EVEN TYPE Arrival


def test_non_biological_relationships(client):
    b = staged(client, "t.ged", fx.ANCESTRY_V1.encode())
    pid = commit(client, b["id"])["project_id"]
    people = persons_by_name(client, pid)
    george = client.ok("get", f"/api/persons/{people['George Ferris']['id']}")
    rels = [(c["related_person_name"], c["relationship_qualifier"]) for c in george["claims"] if c["relationship_type"] == "child"]
    assert ("Zoë Łukasiewicz", "step") in rels and ("Margarethe Fehrs", None) in rels   # not stated in the file → not assumed
    stmt = next(c["statement"] for c in george["claims"] if c["related_person_name"] == "Margarethe Fehrs" and c["relationship_type"] == "child")
    assert "Ancestry" in stmt and "biological" in stmt
    assert not george["conflicts"]  # step-mother is not counted as a third biological parent
    wang = client.ok("get", f"/api/persons/{people['王 秀英']['id']}")
    assert {c["relationship_qualifier"] for c in wang["claims"] if c["relationship_type"] == "child"} == {"adopted"}
    assert any(c["value_text"] == "Adoption" for c in wang["claims"])   # 1 ADOP Y
    assert all(c["status"] == "tentative" for c in wang["claims"] if c["claim_type"] == "relationship")


def test_ftm_media_matching_missing_ambiguous_and_unreferenced(client):
    b = staged(client, "ferris.ged", fx.FTM.encode(), media=fx.FTM_MEDIA)
    mp = b["plan"]["media"]
    summary = mp["summary"]
    assert summary.get("matched") == 2 and summary.get("missing") == 1 and summary.get("ambiguous") == 1
    assert "Unreferenced/random.png" in mp["unreferenced_supplied"]
    done = commit(client, b["id"])
    rep = done["report"]
    assert rep["media_summary"]["matched"] == 2 and rep["stats"]["media_copied"] == 2
    henry = persons_by_name(client, done["project_id"])["Henry Ferris"]
    full = client.ok("get", f"/api/persons/{henry['id']}")
    assert {a["original_name"] for a in full["attachments"]} == {"birth-register.png", "henry.jpg"}
    # Unreferenced file is never attached to anyone
    for p in client.ok("get", f"/api/projects/{done['project_id']}/persons"):
        assert "random.png" not in {a["original_name"] for a in client.ok("get", f"/api/persons/{p['id']}")["attachments"]}
    # Ambiguous media goes to review; choosing a candidate attaches it
    item = next(r for r in done["review"] if r["kind"] == "ambiguous_media")
    r = client.post(f"/api/imports/review/{item['id']}/decide", json={"accept": True, "choice": "Other Folder/portrait.jpg"})
    assert r.status_code == 200
    full = client.ok("get", f"/api/persons/{henry['id']}")
    assert "portrait.jpg" in {a["original_name"] for a in full["attachments"]}
    thomas = persons_by_name(client, done["project_id"])["Thomas Ferris"]
    t = client.ok("get", f"/api/persons/{thomas['id']}")
    assert {c["relationship_qualifier"] for c in t["claims"] if c["relationship_type"] == "child"} == {"step", "biological"}


def test_ftm2019_bom_photo_link_and_fsid(client):
    b = staged(client, "gates.ged", fx.FTM2019, media={"Gates Media/lydia.jpg": fx.JPG})
    assert b["plan"]["detection"]["product"] == "ftm" and b["plan"]["media"]["summary"] == {"matched": 1}
    done = commit(client, b["id"])
    lydia = persons_by_name(client, done["project_id"])["Lydia Gates"]
    full = client.ok("get", f"/api/persons/{lydia['id']}")
    assert [a["original_name"] for a in full["attachments"]] == ["lydia.jpg"]   # via _PHOTO pointer
    src = client.ok("get", f"/api/sources/{full['claims'][0]['evidence'][0]['source_id']}")
    assert src["url"].startswith("https://search.ancestry.com/") and "Justification: Age at death" in src["provenance_note"]
    prov = client.ok("get", f"/api/imports/provenance/person/{lydia['id']}")
    assert "FSID:ABCD-123" in prov["record"]["stable_keys"]


def test_shared_media_item_reaches_every_linked_person_and_ancestry_citation_tags(client):
    text = fx.ANCESTRY_V1.replace("""0 @I112187149803@ INDI
1 NAME Zoë /Łukasiewicz/""", """0 @I112187149803@ INDI
1 OBJE @O1@
1 NAME Zoë /Łukasiewicz/""").replace("""1 MARR
2 DATE 1886""", """1 MARR
2 DATE 1886
2 SOUR @S94982896@
3 PAGE Marriage register
3 _HPID 1,1234::111
3 _WPID 1,1234::222""").replace("1 _APID 1,6742::0", "1 _APID 1,6742::0\n1 CALN 12-345")
    b = staged(client, "t.ged", text.encode())
    paths = {u["path"] for u in b["plan"]["unsupported"]}
    assert not any("_HPID" in p or "_WPID" in p or "CALN" in p for p in paths)
    done = commit(client, b["id"])
    rows_ = [m for m in done["report"]["media"] if "0f67aeca" in m["file_ref"]]
    assert len(rows_) == 2 and {m["owner_xref"] for m in rows_} == {"@I112187149801@", "@I112187149803@"}
    src = next(s_ for s_ in client.ok("get", f"/api/projects/{done['project_id']}/sources") if s_["page_ref"] == "Marriage register")
    assert "call number 12-345" in client.ok("get", f"/api/sources/{src['id']}")["provenance_note"]


def test_media_zip_and_remote_references_not_fetched(client):
    b = staged(client, "t.ged", fx.ANCESTRY_V1.encode(), media={"media.zip": fx.zip_bytes({"photos/a.png": fx.PNG})})
    assert {i["status"] for i in b["plan"]["media"]["items"]} == {"not_in_export"}
    assert b["plan"]["media"]["unreferenced_supplied"] == ["photos/a.png"]   # never attached by guesswork
    done = commit(client, b["id"])
    assert done["report"]["media_summary"] == {"not_in_export": 2}
    remote = fx.FTM.replace("2 FILE portrait.jpg", "2 FILE https://www.ancestry.com/mediaui-viewer/x.jpg")
    b = staged(client, "r.ged", remote.encode())
    assert "remote_not_fetched" in b["plan"]["media"]["summary"]


def test_rootsmagic_ansel_uid_pedi_and_relative_media(client):
    b = staged(client, "rm.ged", fx.ROOTSMAGIC_ANSEL, media={"media/scan.png": fx.PNG})
    assert b["plan"]["detection"]["product"] == "rootsmagic" and b["encoding"] == "ansel"
    done = commit(client, b["id"])
    people = persons_by_name(client, done["project_id"])
    jose = client.ok("get", f"/api/persons/{people['José García']['id']}")
    birth = next(c for c in jose["claims"] if c["claim_type"] == "birth")
    assert birth["date_text"] == "1750/51" and (birth["year_from"], birth["year_to"]) == (1750, 1751)
    assert "preferred" in birth["status_note"]
    assert {c["relationship_qualifier"] for c in jose["claims"] if c["relationship_type"] == "child"} == {"adopted"}
    assert [a["original_name"] for a in jose["attachments"]] == ["scan.png"]


def test_original_file_preserved_byte_for_byte(client):
    b = staged(client, "rm.ged", fx.ROOTSMAGIC_ANSEL)
    r = client.get(f"/api/imports/{b['id']}/original")
    assert r.status_code == 200 and r.content == fx.ROOTSMAGIC_ANSEL


# ------------------------------------------------------------------ repeat imports

def test_repeat_import_without_duplicates_and_with_review(client):
    first = commit(client, staged(client, "t.ged", fx.ANCESTRY_V1.encode())["id"])
    pid, lineage = first["project_id"], first["lineage_id"]
    before = persons_by_name(client, pid)
    josiah_id = before["Josiah Ferris"]["id"]
    # Local edit to a fact and to the person's notes
    j = client.ok("get", f"/api/persons/{josiah_id}")
    death = next(c for c in j["claims"] if c["claim_type"] == "death")
    client.ok("patch", f"/api/claims/{death['id']}", json={"statement": "My own reading of the register"})

    # Same file again → nothing duplicated
    again = staged(client, "t.ged", fx.ANCESTRY_V1.encode(), lineage_id=lineage)
    assert again["plan"]["repeat"]["stats"]["unchanged"] == 6
    again = commit(client, again["id"])
    assert again["report"]["stats"].get("people_created", 0) == 0 and again["report"]["stats"].get("facts_added", 0) == 0
    assert again["review"] == [] and "facts_missing_from_export" not in again["report"]["stats"]
    assert len(client.ok("get", f"/api/projects/{pid}/persons")) == 6
    assert len(client.ok("get", f"/api/projects/{pid}/sources")) == 1

    # Changed export
    v2 = staged(client, "t-v2.ged", fx.ANCESTRY_V2.encode(), lineage_id=lineage)
    rp = v2["plan"]["repeat"]
    assert rp["stats"]["new"] == 1          # Clara
    assert rp["stats"]["uncertain"] == 2    # Margarethe under a new id; @I105@ now a different person
    assert rp["missing_count"] >= 1
    v2 = commit(client, v2["id"])
    people = client.ok("get", f"/api/projects/{pid}/persons")
    names = [p["display_name"] for p in people]
    assert names.count("Josiah Ferris") == 1 and "Clara Ferris" in names
    assert names.count("Margarethe Fehrs") == 2   # imported separately, NOT merged automatically
    j = client.ok("get", f"/api/persons/{josiah_id}")
    assert any(c["claim_type"] == "residence" and c["date_text"] == "1900" for c in j["claims"])   # new fact added
    assert any(c["date_text"] == "1849" for c in j["claims"])   # removed-in-source fact kept
    death = next(c for c in j["claims"] if c["claim_type"] == "death")
    assert death["statement"] == "My own reading of the register"   # local edit preserved
    kinds = {r["kind"] for r in v2["review"]}
    assert {"uncertain_match", "removed_in_source"} <= kinds

    # Resolve: Margarethe is the same person → explicit decision moves facts onto the earlier person
    item = next(r for r in v2["review"] if r["kind"] == "uncertain_match" and "Margarethe" in r["summary"])
    client.ok("post", f"/api/imports/review/{item['id']}/decide", json={"accept": True})
    assert [p["display_name"] for p in client.ok("get", f"/api/projects/{pid}/persons")].count("Margarethe Fehrs") == 1
    # Walter reusing @I105@ is a different person → keep separate
    walter = next(r for r in v2["review"] if r["kind"] == "uncertain_match" and "Walter" in r["summary"])
    client.ok("post", f"/api/imports/review/{walter['id']}/decide", json={"accept": False})
    # Removed fact: mark rejected on review (kept for the record)
    rem = next(r for r in v2["review"] if r["kind"] == "removed_in_source" and r["entity_type"] == "claim")
    client.ok("post", f"/api/imports/review/{rem['id']}/decide", json={"accept": True})
    assert client.ok("get", f"/api/persons/{josiah_id}")["claims"]
    # Third import of v2: everything recognised, no new review for the resolved items
    v3 = staged(client, "t-v2.ged", fx.ANCESTRY_V2.encode(), lineage_id=lineage)
    assert v3["plan"]["repeat"]["stats"]["new"] == 0 and v3["plan"]["repeat"]["stats"]["uncertain"] == 0


def test_identifiers_are_scoped_to_lineage(client):
    a = commit(client, staged(client, "a.ged", fx.ANCESTRY_V1.encode())["id"])
    # A different tree that happens to reuse @I101@ is a separate lineage/project
    other_tree = fx.ANCESTRY_V1.replace("Ferris Family Tree (fictional)", "Another tree").replace("RIN 123456789", "RIN 999")
    b = commit(client, staged(client, "b.ged", other_tree.encode())["id"])
    assert a["project_id"] != b["project_id"] and a["lineage_id"] != b["lineage_id"]
    assert len(client.ok("get", f"/api/projects/{a['project_id']}/persons")) == 6
    assert len(client.ok("get", f"/api/projects/{b['project_id']}/persons")) == 6


# ------------------------------------------------------------------ undo

def test_undo_first_import_removes_project(client):
    b = commit(client, staged(client, "ferris.ged", fx.FTM.encode(), media=fx.FTM_MEDIA)["id"])
    pid = b["project_id"]
    r = client.post(f"/api/imports/{b['id']}/undo")
    assert r.status_code == 200 and r.json()["project_deleted"]
    assert all(p["id"] != pid for p in client.ok("get", "/api/projects"))
    assert not (client.app.state.settings.attachments_dir / pid).exists()


def test_undo_repeat_import_restores_previous_state_and_keeps_local_edits(client):
    first = commit(client, staged(client, "t.ged", fx.ANCESTRY_V1.encode())["id"])
    pid, lineage = first["project_id"], first["lineage_id"]
    v2 = commit(client, staged(client, "t2.ged", fx.ANCESTRY_V2.encode(), lineage_id=lineage)["id"])
    assert "Clara Ferris" in persons_by_name(client, pid)
    # Undo of the first batch is refused while a later one exists
    assert client.post(f"/api/imports/{first['id']}/undo").status_code == 422
    clara = persons_by_name(client, pid)["Clara Ferris"]
    client.ok("patch", f"/api/persons/{clara['id']}", json={"notes": "I added this note"})
    r = client.ok("post", f"/api/imports/{v2['id']}/undo")
    assert not r["project_deleted"]
    people = persons_by_name(client, pid)
    assert "Clara Ferris" in people          # kept because edited locally
    assert any(k["id"] == clara["id"] for k in r["kept_because_edited"])
    j = client.ok("get", f"/api/persons/{people['Josiah Ferris']['id']}")
    assert not any(c["claim_type"] == "residence" and c["date_text"] == "1900" for c in j["claims"])   # v2 fact removed


# ------------------------------------------------------------------ safety

def test_zip_slip_symlink_and_bomb_are_blocked(client):
    b = staged(client, "evil.zip", fx.evil_zip())
    skipped = {s["name"] for s in b["media"]["skipped"]}
    assert {"../../escape.png", "/abs/path.png", "link.png"} <= skipped
    root = client.app.state.settings.data_dir
    assert not (root.parent / "escape.png").exists()
    r = upload(client, "bomb.zip", fx.bomb_zip())
    assert r.status_code == 422 and "ZIP bomb" in r.json()["detail"]


def test_custom_tag_content_is_stored_as_text(client):
    b = staged(client, "t.ged", fx.ANCESTRY_V1.encode())
    ex = next(u for u in b["plan"]["unsupported"] if u["path"] == "INDI._CUSTOMTAG")
    assert ex["example"]["text"] == "1 _CUSTOMTAG Preserve me"
    done = commit(client, b["id"])
    j = persons_by_name(client, done["project_id"])["Josiah Ferris"]
    prov = client.ok("get", f"/api/imports/provenance/person/{j['id']}")
    raw = json.dumps(prov["record"]["raw"])
    assert "_CUSTOMTAG" in raw and "<script>alert('x')</script>" in raw   # preserved verbatim, rendered as text by the UI


def test_backup_includes_original_import(client):
    b = commit(client, staged(client, "t.ged", fx.ANCESTRY_V1.encode())["id"])
    bk = client.ok("post", "/api/backups")
    import zipfile
    with zipfile.ZipFile(client.app.state.settings.backups_dir / bk["name"]) as z:
        assert any(n.startswith("imports/") and n.endswith("/original/t.ged") for n in z.namelist())
    _ = b


def test_report_download_and_checked_flag(client):
    b = commit(client, staged(client, "t.ged", fx.ANCESTRY_V1.encode())["id"])
    rep = client.get(f"/api/imports/{b['id']}/report.json").json()
    for k in ("stats", "media_summary", "failures", "unsupported", "profiles", "warnings"):
        assert k in rep["report"]
    assert rep["report"]["checked_at"] is None
    ok = client.ok("post", f"/api/imports/{b['id']}/checked", json={"checked": True})
    assert ok["report"]["checked_at"]


@pytest.mark.parametrize("data", [fx.ANCESTRY_V1.encode(), fx.FTM.encode(), fx.ROOTSMAGIC_ANSEL])
def test_imports_are_deterministic(client, data):
    a = staged(client, "x.ged", data)["plan"]
    b = staged(client, "x.ged", data)["plan"]
    assert json.dumps(a["counts"]) == json.dumps(b["counts"]) and a["unsupported"] == b["unsupported"]
