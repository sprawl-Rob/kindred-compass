"""Seed updates are idempotent and preserve user edits."""
import copy

from app import seeding
from app.db import connect


def test_seed_is_idempotent(client):
    conn = connect(client.app.state.settings.db_path)
    try:
        n1 = conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
        report = seeding.apply_directory_seed(conn)
        n2 = conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
        assert n1 == n2
        assert not report["inserted"] and not report["updated"]
    finally:
        conn.close()


def test_seed_update_preserves_user_edits(client):
    s = client.ok("post", "/api/directory/search", json={"q": "FreeCEN"})
    c = next(x for g in s["groups"].values() for x in g)
    client.ok("patch", f"/api/directory/collections/{c['id']}", json={"limitations": "My local note about coverage"})
    client.ok("post", f"/api/directory/collections/{c['id']}/archive", json={"archived": True})

    seed = copy.deepcopy(seeding.load_seed())
    seed["version"] += 1
    entry = next(e for e in seed["collections"] if e["key"] == "freecen")
    entry["limitations"] = "Seed changed limitations"
    entry["description"] = "Seed changed description"
    conn = connect(client.app.state.settings.db_path)
    try:
        report = seeding.apply_directory_seed(conn, seed)
    finally:
        conn.close()
    assert {"key": "freecen", "field": "limitations"} in report["preserved_user_edits"]
    after = client.ok("get", f"/api/directory/collections/{c['id']}")
    assert after["limitations"] == "My local note about coverage"   # user edit kept
    assert after["description"] == "Seed changed description"      # non-edited field updated
    assert after["archived"] == 1                                   # archive not undone
    assert any(h["source"] == "seed" for h in after["history"])


def test_user_created_entries_untouched_by_seed(client):
    prov = client.ok("post", "/api/directory/providers", json={"name": "Fitchburg Historical Society", "provider_type": "historical_society"})
    col = client.ok("post", "/api/directory/collections", json={
        "provider_id": prov["id"], "name": "Fitchburg town records", "url": "https://example.org/fhs", "entry_kind": "repository",
        "geo": [{"country": "United States", "region": "Massachusetts", "county": "Worcester", "municipality": "Fitchburg"}]})
    conn = connect(client.app.state.settings.db_path)
    try:
        seeding.apply_directory_seed(conn)
    finally:
        conn.close()
    again = client.ok("get", f"/api/directory/collections/{col['id']}")
    assert again["name"] == "Fitchburg town records" and again["origin"] == "user"
    assert again["verification_status"] == "needs_verification"


def test_verify_records_date_and_source(client):
    s = client.ok("post", "/api/directory/search", json={"q": "MyHeritage"})
    c = next(x for g in s["groups"].values() for x in g)
    v = client.ok("post", f"/api/directory/collections/{c['id']}/verify", json={"status": "verified", "source_note": "Checked help pages", "checked_on": "2026-10-05"})
    assert v["verification_status"] == "verified" and v["last_verified"] == "2026-10-05" and v["verification_source"] == "Checked help pages"


def test_directory_validation(client):
    prov = client.ok("post", "/api/directory/providers", json={"name": "P"})
    bad = client.post("/api/directory/collections", json={"provider_id": prov["id"], "name": "x", "url": "javascript:alert(1)"})
    assert bad.status_code == 422
    bad = client.post("/api/directory/collections", json={"provider_id": prov["id"], "name": "x", "url": "https://a.b", "record_types": ["nonsense"]})
    assert bad.status_code == 422
    bad = client.post("/api/directory/collections", json={"provider_id": prov["id"], "name": "x", "url": "https://a.b", "dates": [{"from": 1900, "to": 1800}]})
    assert bad.status_code == 422
