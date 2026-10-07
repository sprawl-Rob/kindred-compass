"""Imported documents: upload, text, discovery (type, fields, people in the tree), filing with a person."""
import time

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

CERT = ["COMMONWEALTH OF MASSACHUSETTS", "CERTIFICATE OF MARRIAGE", "Groom: Oscar Lindqvist", "Bride: Greta Holm",
        "Date of Marriage: June 2, 1906", "Place of Marriage: Fitchburg", "Father of Groom: Nils Lindqvist", "Officiant: Rev. J. Olson"]


def _pdf(lines):
    w = PdfWriter()
    page = w.add_blank_page(612, 792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    c = "".join(f"BT /F1 12 Tf 72 {720 - i * 20} Td ({l}) Tj ET\n" for i, l in enumerate(lines))
    st = DecodedStreamObject()
    st.set_data(c.encode("latin-1"))
    page[NameObject("/Contents")] = w._add_object(st)
    import io
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def _wait(c, did):
    for _ in range(100):
        d = c.ok("get", f"/api/documents/{did}")
        if d["status"] != "processing":
            return d
        time.sleep(0.05)
    raise AssertionError("still processing")


def _tree(c):
    pid = c.ok("post", "/api/projects", json={"name": "Docs"})["id"]
    oscar = c.ok("post", f"/api/projects/{pid}/persons", json={"names": [{"given": "Oscar", "surname": "Lindqvist"}], "sex": "M", "living_status": "deceased"})["id"]
    greta = c.ok("post", f"/api/projects/{pid}/persons", json={"names": [{"given": "Margareta", "surname": "Holm"}], "sex": "F", "living_status": "deceased"})["id"]
    return pid, oscar, greta


def test_upload_read_discover_and_file_a_marriage_certificate(make_client):
    c = make_client()
    pid, oscar, greta = _tree(c)
    r = c.c.post(f"/api/projects/{pid}/documents", files=[("files", ("marriage.pdf", _pdf(CERT), "application/pdf"))], headers={"X-Kindred": "1"})
    assert r.status_code == 200, r.text
    d = _wait(c, r.json()["documents"][0]["id"])
    assert d["status"] == "ready" and d["doc_type"] == "marriage" and "Groom: Oscar Lindqvist" in d["text"]
    det = d["detected"]
    assert det["fields"]["groom"] == "Oscar Lindqvist" and det["fields"]["marriage_date"] == "June 2, 1906"
    assert {m["name"] for m in det["mentioned"]} >= {"Oscar Lindqvist", "Margareta Holm"}     # Greta = Margareta
    assert det["title"] == "Marriage certificate — Oscar Lindqvist & Greta Holm — 1906"
    # filing it with the bride: the groom becomes the spouse
    pv = c.ok("get", f"/api/documents/{d['id']}/attach-preview", params={"person_id": greta})
    assert any(f["claim_type"] == "marriage" and f["date_text"] == "June 2, 1906" for f in pv["facts"])
    sp = next(p for p in pv["people"] if p["name"] == "Oscar Lindqvist")
    assert sp["relationship"] == "spouse" and sp["action"] == "add"       # not yet linked as spouses in the tree
    filed = c.ok("post", f"/api/documents/{d['id']}/attach", json={"person_id": greta, "source": pv["source"], "facts": pv["facts"],
                                                                     "people": [{**sp, "action": "skip"}], "also": [oscar]})
    assert filed["status"] == "attached" and filed["saved"]["facts"] >= 1 and set(filed["person_ids"]) == {greta, oscar}
    src = c.ok("get", f"/api/sources/{filed['source_id']}")
    assert src["record_format"] == "original_image" and "Groom" in src["transcription"]
    assert c.ok("get", f"/api/projects/{pid}/documents", params={"person_id": oscar})[0]["id"] == d["id"]
    assert c.ok("get", f"/api/projects/{pid}/documents", params={"status": "inbox"}) == []


def test_corrected_text_is_rediscovered_and_documents_can_be_deleted(make_client):
    c = make_client()
    pid, oscar, _ = _tree(c)
    r = c.c.post(f"/api/projects/{pid}/documents", files=[("files", ("note.txt", b"a scrap of paper", "text/plain"))], headers={"X-Kindred": "1"})
    d = _wait(c, r.json()["documents"][0]["id"])
    assert d["doc_type"] == "other" and d["detected"]["mentioned"] == []
    d = c.ok("patch", f"/api/documents/{d['id']}", json={"transcription": "CERTIFICATE OF DEATH\nName of Deceased: Oscar Lindqvist\nDate of Death: 1933"})
    assert d["doc_type"] == "death" and d["detected"]["subjects"] == [oscar]
    c.ok("delete", f"/api/documents/{d['id']}")
    assert c.ok("get", f"/api/projects/{pid}/documents") == []


def test_unsupported_files_are_reported(make_client):
    c = make_client()
    pid, *_ = _tree(c)
    r = c.c.post(f"/api/projects/{pid}/documents", files=[("files", ("x.exe", b"MZ....", "application/octet-stream"))], headers={"X-Kindred": "1"})
    assert r.status_code == 200 and r.json()["documents"] == [] and "not accepted" in r.json()["errors"][0]["error"]
