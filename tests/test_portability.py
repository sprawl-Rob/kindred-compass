"""Persistence, exports, imports, CSV, backup & restore (with attachments)."""
import csv
import io
import json
import zipfile

from app import portability as port

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def add_source_with_attachment(client, pid):
    src = client.ok("post", f"/api/projects/{pid}/sources", json={"title": "Scan of register", "repository": "Archive"})
    r = client.c.post(f"/api/projects/{pid}/attachments", headers={"X-Kindred": "1"},
                      data={"owner_type": "source", "owner_id": src["id"]}, files={"file": ("scan.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    return src, r.json()


def test_data_persists_across_restart(make_client):
    c1 = make_client()
    p = c1.ok("post", "/api/projects", json={"name": "Persist me"})
    c1.ok("post", f"/api/projects/{p['id']}/persons", json={"display_name": "Ann"})
    c2 = make_client()  # new app instance on the same data dir
    names = [x["name"] for x in c2.ok("get", "/api/projects")]
    assert "Persist me" in names
    assert c2.ok("get", f"/api/projects/{p['id']}/persons")[0]["display_name"] == "Ann"


def test_full_export_import_roundtrip(make_client, tmp_path):
    c = make_client()
    p = c.ok("post", "/api/projects", json={"name": "Roundtrip"})
    c.ok("post", f"/api/projects/{p['id']}/persons", json={"display_name": "Ann"})
    doc = c.ok("get", "/api/export/full.json")
    assert doc["format"] == "kindred-compass-export" and "projects" in doc["tables"]
    assert "api_key" not in json.dumps(doc).lower()
    c.ok("delete", f"/api/projects/{p['id']}")
    assert all(x["name"] != "Roundtrip" for x in c.ok("get", "/api/projects"))
    r = c.c.post("/api/import/full", headers={"X-Kindred": "1"}, data={"confirm": "REPLACE"},
                 files={"file": ("e.json", json.dumps(doc).encode(), "application/json")})
    assert r.status_code == 200, r.text
    assert r.json()["safety_backup"].endswith(".zip")
    assert any(x["name"] == "Roundtrip" for x in c.ok("get", "/api/projects"))


def test_full_import_requires_confirmation_and_valid_file(client):
    r = client.c.post("/api/import/full", headers={"X-Kindred": "1"}, data={"confirm": "no"}, files={"file": ("e.json", b"{}", "application/json")})
    assert r.status_code == 422
    r = client.c.post("/api/import/full", headers={"X-Kindred": "1"}, data={"confirm": "REPLACE"}, files={"file": ("e.json", b"not json", "application/json")})
    assert r.status_code == 422
    r = client.c.post("/api/import/full", headers={"X-Kindred": "1"}, data={"confirm": "REPLACE"},
                      files={"file": ("e.json", json.dumps({"format": "kindred-compass-export", "schema_version": 1, "tables": {"evil": []}}).encode(), "application/json")})
    assert r.status_code == 422


def test_project_export_import_with_attachment(client, project):
    pid = project["id"]
    src, att = add_source_with_attachment(client, pid)
    person = client.ok("post", f"/api/projects/{pid}/persons", json={"display_name": "Ann", "claims": [{"claim_type": "birth", "date_text": "1850"}]})
    claim = client.ok("get", f"/api/persons/{person['id']}")["claims"][0]
    client.ok("post", f"/api/claims/{claim['id']}/evidence", json={"source_id": src["id"], "stance": "supports"})
    doc = client.ok("get", f"/api/projects/{pid}/export.json")
    assert doc["attachment_files"]
    r = client.c.post("/api/import/project", headers={"X-Kindred": "1"}, files={"file": ("p.json", json.dumps(doc).encode(), "application/json")})
    assert r.status_code == 200, r.text
    new_pid = r.json()["project_id"]
    assert new_pid != pid
    people = client.ok("get", f"/api/projects/{new_pid}/persons")
    assert people[0]["display_name"] == "Ann" and people[0]["id"] != person["id"]
    srcs = client.ok("get", f"/api/projects/{new_pid}/sources")
    s2 = client.ok("get", f"/api/sources/{srcs[0]['id']}")
    assert s2["claims"] and s2["attachments"]
    dl = client.get(f"/api/attachments/{s2['attachments'][0]['id']}/download")
    assert dl.status_code == 200 and dl.content == PNG
    # original untouched
    assert len(client.ok("get", f"/api/projects/{pid}/persons")) == 1


def test_backup_and_restore_with_attachments(client, project):
    pid = project["id"]
    src, att = add_source_with_attachment(client, pid)
    b = client.ok("post", "/api/backups")
    with zipfile.ZipFile(client.app.state.settings.backups_dir / b["name"]) as z:
        names = z.namelist()
        assert "manifest.json" in names and "kindred.sqlite3" in names
        assert any(n.startswith("attachments/") for n in names)
    # Change data after the backup, then restore
    client.ok("delete", f"/api/sources/{src['id']}")
    assert client.get(f"/api/attachments/{att['id']}/download").status_code == 404  # attachment removed with its source
    assert not (client.app.state.settings.attachments_dir / att["stored_path"]).exists()
    client.ok("post", "/api/projects", json={"name": "Made after backup"})
    r = client.c.post("/api/backups/restore", headers={"X-Kindred": "1"}, data={"name": b["name"], "confirm": "RESTORE"})
    assert r.status_code == 200, r.text
    assert r.json()["safety_backup"].startswith("kindred-backup-")
    names = [p["name"] for p in client.ok("get", "/api/projects")]
    assert "Made after backup" not in names and "Test project" in names
    s = client.ok("get", f"/api/sources/{src['id']}")
    dl = client.get(f"/api/attachments/{s['attachments'][0]['id']}/download")
    assert dl.status_code == 200 and dl.content == PNG


def test_restore_rejects_tampered_or_unsafe_archives(client, tmp_path):
    b = client.ok("post", "/api/backups")
    src = client.app.state.settings.backups_dir / b["name"]
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(bad, "w") as zout:
        for n in zin.namelist():
            data = zin.read(n)
            if n == "kindred.sqlite3":
                data = data[:-10] + b"x" * 10
            zout.writestr(n, data)
    r = client.c.post("/api/backups/restore", headers={"X-Kindred": "1"}, data={"confirm": "RESTORE"}, files={"file": ("bad.zip", bad.read_bytes(), "application/zip")})
    assert r.status_code == 422 and "checksum" in r.json()["detail"]
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": "kindred-compass-backup", "schema_version": 1, "files": {}}))
        z.writestr("kindred.sqlite3", b"")
        z.writestr("../escape.txt", b"x")
    r = client.c.post("/api/backups/restore", headers={"X-Kindred": "1"}, data={"confirm": "RESTORE"}, files={"file": ("evil.zip", evil.read_bytes(), "application/zip")})
    assert r.status_code == 422


def test_csv_exports(client, project):
    pid = project["id"]
    client.ok("post", f"/api/projects/{pid}/log", json={"resource_text": "=HYPERLINK(\"http://evil\")", "query_text": "Smith", "outcome": "no_result"})
    text = client.get(f"/api/projects/{pid}/log.csv").text
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][0] == "searched_on" and len(rows) == 2
    assert rows[1][5].startswith("'=")  # formula injection neutralised
    d = client.get("/api/directory/export.csv").text
    drows = list(csv.reader(io.StringIO(d)))
    assert drows[0] == port.DIRECTORY_CSV_COLUMNS and len(drows) > 50
