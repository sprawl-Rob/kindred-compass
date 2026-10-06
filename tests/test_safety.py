"""Safe handling of user input, attachments, and cross-site requests."""
from fastapi.testclient import TestClient

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def upload(client, pid, owner_id, name, data, owner_type="source"):
    return client.c.post(f"/api/projects/{pid}/attachments", headers={"X-Kindred": "1"},
                         data={"owner_type": owner_type, "owner_id": owner_id}, files={"file": (name, data, "application/octet-stream")})


def test_attachment_type_and_content_checks(client, project):
    pid = project["id"]
    src = client.ok("post", f"/api/projects/{pid}/sources", json={"title": "S"})
    assert upload(client, pid, src["id"], "x.html", b"<script>alert(1)</script>").status_code == 422
    assert upload(client, pid, src["id"], "x.svg", b"<svg onload=alert(1)>").status_code == 422
    assert upload(client, pid, src["id"], "fake.png", b"<html>").status_code == 422      # magic bytes mismatch
    assert upload(client, pid, src["id"], "empty.txt", b"").status_code == 422
    r = upload(client, pid, src["id"], "../../../etc/passwd.png", PNG)
    assert r.status_code == 200
    a = r.json()
    assert ".." not in a["stored_path"] and "/" not in a["original_name"]
    assert a["stored_path"].startswith(pid + "/")
    dl = client.get(f"/api/attachments/{a['id']}/download")
    assert dl.headers["content-disposition"].startswith("attachment")
    assert dl.headers["x-content-type-options"] == "nosniff"


def test_attachment_owner_must_belong_to_project(client, project):
    other = client.ok("post", "/api/projects", json={"name": "Other"})
    src = client.ok("post", f"/api/projects/{other['id']}/sources", json={"title": "S"})
    assert upload(client, project["id"], src["id"], "a.png", PNG).status_code == 404


def test_writes_require_csrf_header(client):
    r = client.c.post("/api/projects", json={"name": "x"})
    assert r.status_code == 403
    r = client.c.post("/api/projects", json={"name": "x"}, headers={"X-Kindred": "1"})
    assert r.status_code == 200


def test_rejects_foreign_host_header(client):
    r = client.c.get("/api/meta", headers={"Host": "evil.example.com"})
    assert r.status_code == 403


def test_security_headers(client):
    r = client.get("/")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"


def test_text_is_stored_literally(client, project):
    pid = project["id"]
    nasty = "Robert'); DROP TABLE persons;-- <img src=x onerror=alert(1)>"
    p = client.ok("post", f"/api/projects/{pid}/persons", json={"display_name": nasty})
    assert client.ok("get", f"/api/persons/{p['id']}")["display_name"] == nasty
    assert len(client.ok("get", f"/api/projects/{pid}/persons")) == 1


def test_input_validation(client, project):
    pid = project["id"]
    assert client.post(f"/api/projects/{pid}/persons", json={}).status_code == 422
    assert client.post(f"/api/projects/{pid}/log", json={"resource_text": "x"}).status_code == 422          # outcome required
    assert client.post(f"/api/projects/{pid}/log", json={"resource_text": "x", "outcome": "bogus"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/log", json={"resource_text": "x", "outcome": "no_result", "result_url": "javascript:x"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/sources", json={"title": "x", "url": "file:///etc/passwd"}).status_code == 422
    assert client.post(f"/api/projects/{pid}/questions", json={"question": "q", "year_from": 1900, "year_to": 1800}).status_code == 422
    assert client.post(f"/api/projects/{pid}/persons", json={"display_name": "x" * 30000}).status_code == 422
    assert client.get("/api/persons/does-not-exist").status_code == 404


def test_backup_download_path_traversal(client):
    assert client.get("/api/backups/..%2F..%2Fkindred.sqlite3/download").status_code == 404
