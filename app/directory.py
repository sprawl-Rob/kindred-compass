"""Resource directory: providers, collections, filtering, maintenance."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import coverage as cov
from .db import Tx, insert, new_id, now_iso, one, rows, to_columns, update
from .taxonomy import ACCESS, RECORD_TYPES, SEARCH_CAPABILITIES

PROVIDER_FIELDS = ["name", "homepage_url", "provider_type", "country", "description", "notes"]
PROVIDER_JSON: list[str] = []

COLLECTION_FIELDS = [
    "provider_id", "name", "url", "description", "entry_kind", "repository_type", "geo_scope", "geo", "dates",
    "date_gaps", "languages", "scripts", "record_types", "capabilities", "evidence_forms", "access_search",
    "access_images", "access_copies", "access_notes", "integration_method", "search_url", "search_url_template",
    "search_link_verified", "search_link_notes", "adapter_key", "terminology", "rights_notes", "limitations",
    "digitization_status", "verification_status", "last_verified", "verification_source", "link_health",
    "link_checked_at", "maintenance_notes", "tags", "pathways",
]
COLLECTION_JSON = [
    "geo", "dates", "date_gaps", "languages", "scripts", "record_types", "capabilities", "evidence_forms",
    "access_search", "access_images", "access_copies", "terminology", "tags", "pathways",
]


class NotFound(Exception):
    pass


class ValidationError(Exception):
    pass


# ---------------------------------------------------------------- validation

def _validate_collection(data: dict) -> None:
    for key in ("record_types",):
        bad = [v for v in data.get(key) or [] if v not in RECORD_TYPES]
        if bad:
            raise ValidationError(f"Unknown record types: {', '.join(bad)}")
    bad = [v for v in data.get("capabilities") or [] if v not in SEARCH_CAPABILITIES]
    if bad:
        raise ValidationError(f"Unknown search capabilities: {', '.join(bad)}")
    for key in ("access_search", "access_images", "access_copies"):
        vals = data.get(key)
        if vals is not None:
            bad = [v for v in vals if v not in ACCESS]
            if bad:
                raise ValidationError(f"Unknown access values in {key}: {', '.join(bad)}")
    for key in ("dates", "date_gaps"):
        for r in data.get(key) or []:
            f, t = r.get("from"), r.get("to")
            if f is not None and t is not None and int(f) > int(t):
                raise ValidationError(f"Date range {f}–{t} is reversed")
    url = data.get("url")
    for k in ("url", "search_url", "search_url_template"):
        v = data.get(k)
        if v and not str(v).startswith(("https://", "http://")):
            raise ValidationError(f"{k} must start with http:// or https://")
    if data.get("search_url_template") and not data.get("search_link_verified"):
        # Unverified templates are allowed to be stored but never used to build links.
        pass
    _ = url


# ---------------------------------------------------------------- providers

def list_providers(conn: sqlite3.Connection, include_archived: bool = False) -> list[dict]:
    sql = "SELECT * FROM providers" + ("" if include_archived else " WHERE archived = 0") + " ORDER BY name COLLATE NOCASE"
    return rows(conn, sql)


def get_provider(conn, pid: str) -> dict:
    p = one(conn, "SELECT * FROM providers WHERE id = ?", (pid,))
    if not p:
        raise NotFound("provider")
    return p


def create_provider(conn, data: dict, origin: str = "user") -> dict:
    if not (data.get("name") or "").strip():
        raise ValidationError("Provider name is required")
    pid = data.get("id") or new_id()
    ts = now_iso()
    vals = {k: data.get(k) for k in PROVIDER_FIELDS if k in data}
    vals.setdefault("provider_type", "other")
    with Tx(conn):
        insert(conn, "providers", {"id": pid, **vals, "origin": origin, "seed_key": data.get("seed_key"),
                                   "seed_version": data.get("seed_version"), "seed_hash": data.get("seed_hash"),
                                   "created_at": ts, "updated_at": ts})
        _history(conn, "provider", pid, origin, "created", vals)
    return get_provider(conn, pid)


def update_provider(conn, pid: str, data: dict, source: str = "user") -> dict:
    cur = get_provider(conn, pid)
    vals = {k: data[k] for k in PROVIDER_FIELDS if k in data and data[k] != cur.get(k)}
    if "archived" in data:
        vals["archived"] = int(bool(data["archived"]))
    if not vals:
        return cur
    if source == "user":
        uf = set(cur.get("user_fields") or []) | {k for k in vals if k != "archived"}
        vals["user_fields_json"] = json.dumps(sorted(uf))
    vals["updated_at"] = now_iso()
    with Tx(conn):
        update(conn, "providers", pid, vals)
        _history(conn, "provider", pid, source, "updated", {k: v for k, v in vals.items() if k != "user_fields_json"})
    return get_provider(conn, pid)


# ---------------------------------------------------------------- collections

def get_collection(conn, cid: str) -> dict:
    c = one(conn, "SELECT c.*, p.name AS provider_name, p.homepage_url AS provider_url FROM collections c "
                  "JOIN providers p ON p.id = c.provider_id WHERE c.id = ?", (cid,))
    if not c:
        raise NotFound("collection")
    c["relations"] = rows(conn, """
        SELECT r.id, r.relation, r.note, CASE WHEN r.a_id = ? THEN r.b_id ELSE r.a_id END AS other_id,
               c2.name AS other_name, p2.name AS other_provider
        FROM collection_relations r
        JOIN collections c2 ON c2.id = CASE WHEN r.a_id = ? THEN r.b_id ELSE r.a_id END
        JOIN providers p2 ON p2.id = c2.provider_id
        WHERE r.a_id = ? OR r.b_id = ?""", (cid, cid, cid, cid))
    c["badges"] = badges(c)
    return c


def all_collections(conn, include_archived: bool = False) -> list[dict]:
    sql = ("SELECT c.*, p.name AS provider_name, p.homepage_url AS provider_url FROM collections c "
           "JOIN providers p ON p.id = c.provider_id")
    if not include_archived:
        sql += " WHERE c.archived = 0 AND p.archived = 0"
    sql += " ORDER BY c.name COLLATE NOCASE"
    out = rows(conn, sql)
    for c in out:
        c["badges"] = badges(c)
    return out


def create_collection(conn, data: dict, origin: str = "user") -> dict:
    if not (data.get("name") or "").strip():
        raise ValidationError("Collection name is required")
    if not data.get("provider_id"):
        raise ValidationError("A provider is required")
    get_provider(conn, data["provider_id"])
    _validate_collection(data)
    cid = data.get("id") or new_id()
    ts = now_iso()
    vals = to_columns({k: data[k] for k in COLLECTION_FIELDS if k in data}, COLLECTION_JSON)
    if data.get("geo") and "geo_scope" not in data:
        vals["geo_scope"] = "listed"
    with Tx(conn):
        insert(conn, "collections", {"id": cid, **vals, "origin": origin, "seed_key": data.get("seed_key"),
                                     "seed_version": data.get("seed_version"), "seed_hash": data.get("seed_hash"),
                                     "created_at": ts, "updated_at": ts})
        _history(conn, "collection", cid, origin, "created", None)
    return get_collection(conn, cid)


def update_collection(conn, cid: str, data: dict, source: str = "user") -> dict:
    cur = get_collection(conn, cid)
    changes = {k: data[k] for k in COLLECTION_FIELDS if k in data and data[k] != cur.get(k)}
    merged = {**cur, **changes}
    _validate_collection(merged)
    vals = to_columns(changes, COLLECTION_JSON)
    if "archived" in data:
        vals["archived"] = int(bool(data["archived"]))
    if not vals:
        return cur
    if source == "user":
        uf = set(cur.get("user_fields") or []) | set(changes)
        vals["user_fields_json"] = json.dumps(sorted(uf))
    vals["updated_at"] = now_iso()
    with Tx(conn):
        update(conn, "collections", cid, vals)
        _history(conn, "collection", cid, source, "archived" if data.get("archived") else "updated",
                 {k: {"from": cur.get(k), "to": v} for k, v in changes.items()})
    return get_collection(conn, cid)


def mark_verified(conn, cid: str, status: str, source_note: str | None, checked_on: str) -> dict:
    """Record a manual verification by the user."""
    from .taxonomy import VERIFICATION_STATUSES
    if status not in VERIFICATION_STATUSES:
        raise ValidationError("Unknown verification status")
    return update_collection(conn, cid, {
        "verification_status": status, "last_verified": checked_on,
        "verification_source": source_note or "Checked manually by user",
    }, source="user")


def add_relation(conn, a_id: str, b_id: str, relation: str, note: str | None = None, origin: str = "user", seed_key: str | None = None) -> dict:
    if a_id == b_id:
        raise ValidationError("A collection cannot relate to itself")
    get_collection(conn, a_id)
    get_collection(conn, b_id)
    rid = new_id()
    insert(conn, "collection_relations", {"id": rid, "a_id": a_id, "b_id": b_id, "relation": relation, "note": note,
                                          "origin": origin, "seed_key": seed_key, "created_at": now_iso()})
    return {"id": rid}


def history(conn, entity_id: str) -> list[dict]:
    return rows(conn, "SELECT * FROM directory_history WHERE entity_id = ? ORDER BY id DESC", (entity_id,))


def _history(conn, etype: str, eid: str, source: str, summary: str, diff: Any) -> None:
    conn.execute("INSERT INTO directory_history (entity_type, entity_id, source, summary, diff_json, created_at) VALUES (?,?,?,?,?,?)",
                 (etype, eid, source, summary, json.dumps(diff, ensure_ascii=False, default=str) if diff is not None else None, now_iso()))


# ---------------------------------------------------------------- badges

def badges(c: dict) -> list[dict]:
    """Practical, honest labels shown on cards."""
    out: list[dict] = []
    s, im = set(c.get("access_search") or []), set(c.get("access_images") or [])
    caps = set(c.get("capabilities") or [])

    def add(label, tone="neutral", hint=None):
        out.append({"label": label, "tone": tone, "hint": hint})

    if s == {"free"}:
        add("Free to search", "good")
    elif "free_account" in s:
        add("Free account", "info", "Searching requires a free login")
    elif "subscription" in s:
        add("Subscription", "warn")
    if "library" in s | im:
        add("Library access", "info", "Available free at some libraries / FamilySearch centers")
    if im and im <= {"subscription", "onsite", "library", "paid_retrieval"} and (s & {"free", "free_account"}):
        add("Images restricted", "warn", "Index may be free, but images need extra access")
    if "onsite" in s and len(s) == 1:
        add("Onsite only", "warn")
    if "request_only" in caps:
        add("Request-only", "warn")
    if "browse_images" in caps and "name_index" not in caps and "full_text" not in caps:
        add("Browse only", "warn", "No name index: you browse page images")
    if "full_text" in caps:
        add("Full-text search", "info")
    if c.get("integration_method") == "documented_api" and c.get("adapter_key"):
        add("Live search in app", "good", "Implemented integration with a documented public API")
    vs = c.get("verification_status")
    if vs == "needs_verification":
        add("Needs verification", "muted", "Details not yet checked against the provider")
    elif vs == "partial":
        add("Partly verified", "muted")
    elif vs == "broken":
        add("Link problem", "bad")
    if c.get("geo_scope") == "unknown" or not c.get("dates"):
        add("Coverage incomplete", "muted", "Some coverage details are not recorded")
    return out


# ---------------------------------------------------------------- filtering

def filter_collections(conn, f: dict) -> dict:
    """Directory search. Returns groups so unknown coverage stays visible.

    f keys: q, country, region, county, municipality, year_from, year_to, record_types[],
            access ('free'|'free_or_account'|'my_access'), remote_only, languages[], capabilities[],
            entry_kinds[], verification[], saved_only, include_archived, subscriptions[] (provider ids)
    """
    items = all_collections(conn, include_archived=bool(f.get("include_archived")))
    q = (f.get("q") or "").strip().lower()
    place = cov.PlaceQuery.from_dict(f)
    yf, yt = f.get("year_from"), f.get("year_to")
    rtypes = set(f.get("record_types") or [])
    caps = set(f.get("capabilities") or [])
    langs = {l.lower() for l in f.get("languages") or []}
    kinds = set(f.get("entry_kinds") or [])
    verif = set(f.get("verification") or [])
    saved_ids = set(f.get("saved_ids") or [])

    groups: dict[str, list] = {"match": [], "partial": [], "unknown": [], "guidance": []}
    hidden_by_preferences: list[dict] = []
    for c in items:
        if q and q not in _haystack(c):
            continue
        if kinds and c["entry_kind"] not in kinds:
            continue
        if verif and c["verification_status"] not in verif:
            continue
        if f.get("saved_only") and c["id"] not in saved_ids:
            continue
        if caps and not caps & set(c["capabilities"] or []):
            continue
        rt_status = "match"
        is_guidance = c["entry_kind"] in ("guide", "directory")
        if rtypes and not is_guidance:
            crt = set(c["record_types"] or [])
            if not crt:
                rt_status = "unknown"
            elif not rtypes & crt:
                continue
        gs, gwhy = cov.geo_match(c["geo_scope"], c["geo"] or [], place)
        ds, dwhy = cov.date_match(c["dates"] or [], yf, yt, c["date_gaps"])
        overall = cov.combine(gs, ds)
        if overall == cov.NONE:
            continue
        if rt_status == "unknown" and overall == cov.MATCH:
            overall = cov.UNKNOWN
        lang_ok = not langs or not c["languages"] or bool(langs & {l.lower() for l in c["languages"]})
        if not lang_ok:
            continue
        c = {**c, "coverage": {"overall": overall, "geo": gs, "geo_why": gwhy, "dates": ds, "dates_why": dwhy,
                               "record_types": rt_status}, "saved": c["id"] in saved_ids}
        # Access preferences narrow the view but are reported, never silently dropped.
        reason = access_excluded(c, f)
        if reason:
            hidden_by_preferences.append({"id": c["id"], "name": c["name"], "provider_name": c["provider_name"], "reason": reason})
            continue
        groups["guidance" if is_guidance else overall].append(c)
    return {"groups": groups, "hidden_by_preferences": hidden_by_preferences,
            "total": sum(len(v) for v in groups.values())}


def access_excluded(c: dict, f: dict) -> str | None:
    access = f.get("access")
    s = set(c.get("access_search") or [])
    if access == "free" and not s & {"free"}:
        return "Not free to search"
    if access == "free_or_account" and not s & {"free", "free_account"}:
        return "Needs payment, library, or onsite access to search"
    if access == "my_access":
        subs = set(f.get("subscriptions") or [])
        if not (s & {"free", "free_account"} or ("subscription" in s and c["provider_id"] in subs)):
            return "Not covered by your subscriptions"
    if f.get("remote_only"):
        caps = set(c.get("capabilities") or [])
        if caps and caps <= {"onsite", "request_only"}:
            return "Onsite or request-only"
        if s == {"onsite"}:
            return "Onsite only"
    return None


def _haystack(c: dict) -> str:
    parts = [c.get("name"), c.get("provider_name"), c.get("description"), c.get("limitations"), c.get("access_notes"),
             " ".join(c.get("tags") or []), " ".join(c.get("terminology") or []),
             " ".join(RECORD_TYPES.get(r, r) for r in c.get("record_types") or []),
             " ".join(" ".join(str(v) for v in g.values() if v) for g in c.get("geo") or [])]
    return " ".join(p for p in parts if p).lower()


# ---------------------------------------------------------------- bookmarks

def saved_ids(conn, project_id: str | None) -> set[str]:
    r = rows(conn, "SELECT collection_id FROM bookmarks WHERE collection_id IS NOT NULL AND (project_id IS NULL OR project_id = ?)", (project_id,))
    return {x["collection_id"] for x in r}
