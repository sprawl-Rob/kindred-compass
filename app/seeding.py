"""Versioned, idempotent seed updates that preserve user edits.

Seed files (app/seed/directory_seed.json) carry a `version`. Applying a seed:

* inserts entries whose seed_key is not yet present;
* updates fields of existing seed entries **only** where the user has not edited
  that field (tracked per entity in user_fields_json);
* never un-archives something the user archived, never deletes anything;
* reports conflicts (seed changed a field the user had edited) so they can be reviewed.

Running the same seed twice changes nothing.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import directory as d
from .db import Tx, insert, new_id, now_iso, one, update

SEED_DIR = Path(__file__).parent / "seed"
DIRECTORY_SEED = SEED_DIR / "directory_seed.json"


def _hash(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def load_seed(path: Path = DIRECTORY_SEED) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_directory_seed(conn, seed: dict | None = None) -> dict:
    seed = seed or load_seed()
    version = int(seed["version"])
    report = {"version": version, "inserted": [], "updated": [], "unchanged": 0, "preserved_user_edits": [], "not_in_seed": []}
    provider_ids: dict[str, str] = {}

    with Tx(conn):
        for p in seed.get("providers", []):
            values = {k: p.get(k) for k in d.PROVIDER_FIELDS if k in p}
            pid = _upsert(conn, "providers", "provider", p["key"], values, [], version, report)
            provider_ids[p["key"]] = pid

        for c in seed.get("collections", []):
            pkey = c["provider"]
            if pkey not in provider_ids:
                row = one(conn, "SELECT id FROM providers WHERE seed_key = ?", (pkey,))
                if not row:
                    raise ValueError(f"Seed collection {c['key']} references unknown provider {pkey}")
                provider_ids[pkey] = row["id"]
            values = {k: c.get(k) for k in d.COLLECTION_FIELDS if k in c and k != "provider_id"}
            values["provider_id"] = provider_ids[pkey]
            if values.get("geo") and "geo_scope" not in values:
                values["geo_scope"] = "listed"
            d._validate_collection(values)
            _upsert(conn, "collections", "collection", c["key"], values, d.COLLECTION_JSON, version, report)

        for r in seed.get("relations", []):
            key = r["key"]
            if one(conn, "SELECT id FROM collection_relations WHERE seed_key = ?", (key,)):
                continue
            a = one(conn, "SELECT id FROM collections WHERE seed_key = ?", (r["a"],))
            b = one(conn, "SELECT id FROM collections WHERE seed_key = ?", (r["b"],))
            if a and b:
                insert(conn, "collection_relations", {"id": new_id(), "a_id": a["id"], "b_id": b["id"], "relation": r["relation"],
                                                      "note": r.get("note"), "origin": "seed", "seed_key": key, "created_at": now_iso()})

        for pw in seed.get("pathways", []):
            ts = now_iso()
            vals = {"title": pw["title"], "summary": pw.get("summary"),
                    "cautions_json": json.dumps(pw.get("cautions", []), ensure_ascii=False),
                    "steps_json": json.dumps(pw.get("steps", []), ensure_ascii=False),
                    "sources_json": json.dumps(pw.get("sources", []), ensure_ascii=False),
                    "last_verified": pw.get("last_verified"), "verification_status": pw.get("verification_status", "needs_verification")}
            existing = one(conn, "SELECT id FROM pathways WHERE seed_key = ?", (pw["key"],))
            if existing:
                update(conn, "pathways", existing["id"], {**vals, "updated_at": ts})
            else:
                insert(conn, "pathways", {"id": new_id(), "seed_key": pw["key"], **vals, "created_at": ts, "updated_at": ts})

        seed_keys = {c["key"] for c in seed.get("collections", [])}
        for row in conn.execute("SELECT seed_key, name FROM collections WHERE origin = 'seed'").fetchall():
            if row["seed_key"] not in seed_keys:
                report["not_in_seed"].append(row["name"])

        conn.execute("INSERT INTO seed_state (name, version, applied_at, report_json) VALUES ('directory', ?, ?, ?) "
                     "ON CONFLICT(name) DO UPDATE SET version = excluded.version, applied_at = excluded.applied_at, report_json = excluded.report_json",
                     (version, now_iso(), json.dumps(report)))
    return report


def _upsert(conn, table: str, etype: str, key: str, values: dict, json_fields: list[str], version: int, report: dict) -> str:
    h = _hash(values)
    cur = one(conn, f"SELECT * FROM {table} WHERE seed_key = ?", (key,))
    ts = now_iso()
    if cur is None:
        eid = new_id()
        cols = d.to_columns(values, json_fields) if json_fields else dict(values)
        insert(conn, table, {"id": eid, "seed_key": key, **cols, "origin": "seed", "seed_version": version, "seed_hash": h,
                             "created_at": ts, "updated_at": ts})
        d._history(conn, etype, eid, "seed", f"created from seed v{version}", None)
        report["inserted"].append(key)
        return eid

    eid = cur["id"]
    if cur.get("seed_hash") == h:
        report["unchanged"] += 1
        return eid
    user_fields = set(cur.get("user_fields") or [])
    changes = {}
    for k, v in values.items():
        if cur.get(k) == v:
            continue
        if k in user_fields:
            report["preserved_user_edits"].append({"key": key, "field": k})
            continue
        changes[k] = v
    cols = d.to_columns(changes, json_fields) if json_fields else dict(changes)
    update(conn, table, eid, {**cols, "seed_version": version, "seed_hash": h, "updated_at": ts})
    if changes:
        d._history(conn, etype, eid, "seed", f"updated from seed v{version}",
                   {k: {"from": cur.get(k), "to": v} for k, v in changes.items()})
        report["updated"].append(key)
    else:
        report["unchanged"] += 1
    return eid


def seed_status(conn) -> dict | None:
    r = one(conn, "SELECT * FROM seed_state WHERE name = 'directory'")
    if r and r.get("report_json"):
        r["report"] = json.loads(r.pop("report_json"))
    return r
