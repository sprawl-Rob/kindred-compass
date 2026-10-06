"""REST API for the directory, workspace, evidence, log, and data portability."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from . import attachments as att
from . import config, demo
from . import directory as d
from . import evidence as ev
from . import names as nm
from . import portability as port
from . import recommend as rec
from . import research_log as rl
from . import seeding
from . import settings_store as st
from . import workspace as ws
from .db import Tx, latest_version, one, rows, today_iso
from .deps import get_conn
from .integrations import ADAPTERS, IntegrationError, build_search_link
from .taxonomy import vocabularies

router = APIRouter()
MAX_IMPORT_BYTES = 200 * 1024 * 1024


# ---------------------------------------------------------------- meta & settings

@router.get("/meta")
def meta(request: Request, conn=Depends(get_conn)):
    s = request.app.state.settings
    return {"app": config.APP_NAME, "version": config.APP_VERSION, "schema_version": latest_version(),
            "vocab": vocabularies(), "seed": seeding.seed_status(conn),
            "adapters": [a.describe() for a in ADAPTERS.values()],
            "storage": {"data_dir": str(s.data_dir), "database": str(s.db_path), "attachments": str(s.attachments_dir), "backups": str(s.backups_dir)},
            "directory_counts": one(conn, """SELECT COUNT(*) AS collections,
                                              SUM(verification_status = 'verified') AS verified,
                                              SUM(verification_status = 'partial') AS partial,
                                              SUM(verification_status = 'needs_verification') AS needs_verification,
                                              (SELECT COUNT(*) FROM providers WHERE archived = 0) AS providers
                                              FROM collections WHERE archived = 0""")}


@router.get("/settings/research-prefs")
def get_prefs(conn=Depends(get_conn)):
    return st.get(conn, "research_prefs")


@router.put("/settings/research-prefs")
def put_prefs(body: dict = Body(...), conn=Depends(get_conn)):
    cur = st.get(conn, "research_prefs")
    if body.get("access") not in (None, "free", "free_or_account", "my_access"):
        raise d.ValidationError("Unknown access preference")
    for k in ("access", "subscriptions", "remote_only", "languages"):
        if k in body:
            cur[k] = body[k]
    st.put(conn, "research_prefs", cur)
    return cur


# ---------------------------------------------------------------- directory

@router.post("/directory/search")
def directory_search(body: dict = Body(default={}), conn=Depends(get_conn)):
    pid = body.get("project_id")
    f = dict(body)
    f["saved_ids"] = list(d.saved_ids(conn, pid))
    if f.get("access") == "my_access":
        f["subscriptions"] = st.get(conn, "research_prefs").get("subscriptions") or []
    return d.filter_collections(conn, f)


@router.get("/directory/collections/{cid}")
def collection_detail(cid: str, conn=Depends(get_conn)):
    c = d.get_collection(conn, cid)
    c["history"] = d.history(conn, cid)[:30]
    c["provider"] = d.get_provider(conn, c["provider_id"])
    c["siblings"] = rows(conn, "SELECT id, name, entry_kind FROM collections WHERE provider_id = ? AND id != ? AND archived = 0 ORDER BY name",
                         (c["provider_id"], cid))
    return c


@router.post("/directory/collections")
def collection_create(body: dict = Body(...), conn=Depends(get_conn)):
    return d.create_collection(conn, body)


@router.patch("/directory/collections/{cid}")
def collection_update(cid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return d.update_collection(conn, cid, body)


@router.post("/directory/collections/{cid}/archive")
def collection_archive(cid: str, body: dict = Body(default={"archived": True}), conn=Depends(get_conn)):
    return d.update_collection(conn, cid, {"archived": bool(body.get("archived", True))})


@router.post("/directory/collections/{cid}/verify")
def collection_verify(cid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return d.mark_verified(conn, cid, body.get("status", "verified"), body.get("source_note"), body.get("checked_on") or today_iso())


@router.post("/directory/collections/{cid}/check-link")
def collection_check_link(cid: str, conn=Depends(get_conn)):
    """User-triggered single link check (one request; records the result)."""
    c = d.get_collection(conn, cid)
    url = c.get("url")
    health, detail = "unknown", ""
    try:
        r = httpx.get(url, follow_redirects=True, timeout=15, headers={"User-Agent": "KindredCompass/1.0 link check"})
        if r.status_code < 400:
            health = "redirect" if str(r.url).rstrip("/") != url.rstrip("/") else "ok"
            detail = f"HTTP {r.status_code}" + (f", now at {r.url}" if health == "redirect" else "")
        elif r.status_code in (401, 403, 429):
            health, detail = "unknown", f"HTTP {r.status_code} — the site blocks automated checks; open it in a browser to confirm"
        else:
            health, detail = "error", f"HTTP {r.status_code}"
    except httpx.HTTPError as e:
        health, detail = "error", type(e).__name__
    from .db import now_iso, update
    update(conn, "collections", cid, {"link_health": health, "link_checked_at": now_iso()})
    d._history(conn, "collection", cid, "verification", f"link check: {health}", {"detail": detail})
    return {"link_health": health, "detail": detail}


@router.post("/directory/collections/{cid}/search-link")
def collection_search_link(cid: str, body: dict = Body(default={}), conn=Depends(get_conn)):
    return build_search_link(d.get_collection(conn, cid), body)


@router.get("/directory/providers")
def providers(include_archived: bool = False, conn=Depends(get_conn)):
    return d.list_providers(conn, include_archived)


@router.post("/directory/providers")
def provider_create(body: dict = Body(...), conn=Depends(get_conn)):
    return d.create_provider(conn, body)


@router.patch("/directory/providers/{pid}")
def provider_update(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return d.update_provider(conn, pid, body)


@router.post("/directory/relations")
def relation_create(body: dict = Body(...), conn=Depends(get_conn)):
    return d.add_relation(conn, body["a_id"], body["b_id"], body.get("relation", "overlaps"), body.get("note"))


@router.delete("/directory/relations/{rid}")
def relation_delete(rid: str, conn=Depends(get_conn)):
    conn.execute("DELETE FROM collection_relations WHERE id = ?", (rid,))
    return {"ok": True}


@router.get("/directory/seed")
def seed_info(conn=Depends(get_conn)):
    seed = seeding.load_seed()
    return {"applied": seeding.seed_status(conn), "available_version": seed["version"]}


@router.post("/directory/seed/apply")
def seed_apply(conn=Depends(get_conn)):
    return seeding.apply_directory_seed(conn)


@router.get("/directory/pathways")
def pathways(conn=Depends(get_conn)):
    out = rows(conn, "SELECT * FROM pathways ORDER BY title")
    keyed = {c["seed_key"]: c for c in rows(conn, "SELECT id, seed_key, name, pathways_json FROM collections WHERE archived = 0")}
    for p in out:
        p["collections"] = [{"id": c["id"], "name": c["name"]} for c in keyed.values() if p["seed_key"] in (c.get("pathways") or [])]
    return out


@router.get("/directory/export.csv")
def directory_csv(conn=Depends(get_conn)):
    return Response(port.directory_csv(conn), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="kindred-directory-{today_iso()}.csv"'})


@router.post("/integrations/{key}/search")
def integration_search(key: str, request: Request, body: dict = Body(...)):
    if key not in ADAPTERS:
        raise d.NotFound("integration")
    adapter = ADAPTERS[key](api_key=request.app.state.creds.get("archive:" + key) if ADAPTERS[key].requires_key else None)
    if not hasattr(adapter, "search_simple"):
        raise d.ValidationError("This archive is searched through research runs")
    return adapter.search_simple(body)


# ---------------------------------------------------------------- projects

@router.get("/projects")
def projects(conn=Depends(get_conn)):
    return ws.list_projects(conn)


@router.post("/projects")
def project_create(body: dict = Body(...), conn=Depends(get_conn)):
    return ws.create_project(conn, {"name": body.get("name"), "description": body.get("description")})


@router.get("/projects/{pid}")
def project_get(pid: str, conn=Depends(get_conn)):
    return ws.get_project(conn, pid)


@router.patch("/projects/{pid}")
def project_update(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.update_project(conn, pid, body)


@router.delete("/projects/{pid}")
def project_delete(pid: str, request: Request, conn=Depends(get_conn)):
    port.create_backup(request.app.state.settings, "before-project-delete")
    ws.get_project(conn, pid)
    att.delete_for_project(conn, request.app.state.settings.attachments_dir, pid)
    ws.delete_project(conn, pid)
    return {"ok": True}


@router.post("/demo/reset")
def demo_reset(conn=Depends(get_conn)):
    return demo.reset_demo(conn)


@router.get("/projects/{pid}/dashboard")
def dashboard(pid: str, conn=Depends(get_conn)):
    p = ws.get_project(conn, pid)
    log = rl.list_log(conn, pid)
    counts = one(conn, """SELECT (SELECT COUNT(*) FROM persons WHERE project_id = ?) AS persons,
                                 (SELECT COUNT(*) FROM sources WHERE project_id = ?) AS sources,
                                 (SELECT COUNT(*) FROM claims WHERE project_id = ?) AS claims,
                                 (SELECT COUNT(*) FROM research_log WHERE project_id = ?) AS searches,
                                 (SELECT COUNT(*) FROM research_log WHERE project_id = ? AND outcome = 'no_result') AS negative""",
                 (pid, pid, pid, pid, pid))
    people = ws.list_persons(conn, pid)
    conflicts = []
    for person in people:
        full = ws.get_person(conn, person["id"])
        for c in full["conflicts"]:
            conflicts.append({**c, "person_id": person["id"], "person_name": person["display_name"]})
    return {"project": p, "counts": counts, "questions": [q for q in ws.list_questions(conn, pid) if q["status"] == "open"],
            "tasks": [t for t in ws.list_tasks(conn, pid) if t["status"] == "todo"][:10], "recent_log": log[:8],
            "people": people, "conflicts": conflicts,
            "follow_ups": [e for e in log if e["outcome"] in ("follow_up", "possible_match")][:8]}


# ---------------------------------------------------------------- places, people, names

@router.get("/projects/{pid}/places")
def places(pid: str, conn=Depends(get_conn)):
    return ws.list_places(conn, pid)


@router.post("/projects/{pid}/places")
def place_create(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.create_place(conn, pid, body)


@router.patch("/places/{place_id}")
def place_update(place_id: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.update_place(conn, place_id, body)


@router.get("/projects/{pid}/persons")
def persons(pid: str, conn=Depends(get_conn)):
    return ws.list_persons(conn, pid)


@router.post("/projects/{pid}/persons")
def person_create(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.create_person(conn, pid, body)


@router.get("/persons/{person_id}")
def person_get(person_id: str, conn=Depends(get_conn)):
    p = ws.get_person(conn, person_id)
    p["log"] = rl.list_log(conn, p["project_id"], person_id=person_id)
    p["attachments"] = att.list_for(conn, "person", person_id)
    return p


@router.patch("/persons/{person_id}")
def person_update(person_id: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.update_person(conn, person_id, body)


@router.delete("/persons/{person_id}")
def person_delete(person_id: str, request: Request, conn=Depends(get_conn)):
    att.delete_for_owner(conn, request.app.state.settings.attachments_dir, "person", person_id)
    ws.delete_person(conn, person_id)
    return {"ok": True}


@router.post("/persons/{person_id}/names")
def name_add(person_id: str, body: dict = Body(...), conn=Depends(get_conn)):
    ws._get(conn, "persons", person_id, "person")
    return ws.add_name(conn, person_id, body)


@router.delete("/names/{name_id}")
def name_delete(name_id: str, conn=Depends(get_conn)):
    ws.delete_name(conn, name_id)
    return {"ok": True}


@router.get("/persons/{person_id}/name-variants")
def name_variants(person_id: str, conn=Depends(get_conn)):
    p = ws.get_person(conn, person_id)
    tried = []
    for e in rl.list_log(conn, p["project_id"], person_id=person_id):
        tried += (e.get("name_variants") or []) + [e.get("query_text") or ""]
    return nm.suggest_for_person(p, tried)


# ---------------------------------------------------------------- claims & evidence

@router.get("/projects/{pid}/claims")
def claims(pid: str, conn=Depends(get_conn)):
    return ws.list_claims(conn, project_id=pid)


@router.post("/projects/{pid}/claims")
def claim_create(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.create_claim(conn, pid, body)


@router.patch("/claims/{cid}")
def claim_update(cid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.update_claim(conn, cid, body)


@router.delete("/claims/{cid}")
def claim_delete(cid: str, conn=Depends(get_conn)):
    ws.delete_claim(conn, cid)
    return {"ok": True}


@router.post("/claims/{cid}/evidence")
def evidence_link(cid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ev.link_evidence(conn, cid, body["source_id"], body)


@router.patch("/evidence/{link_id}")
def evidence_update(link_id: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ev.update_link(conn, link_id, body)


@router.delete("/evidence/{link_id}")
def evidence_unlink(link_id: str, conn=Depends(get_conn)):
    ev.unlink(conn, link_id)
    return {"ok": True}


@router.get("/projects/{pid}/sources")
def sources(pid: str, conn=Depends(get_conn)):
    return ev.list_sources(conn, pid)


@router.post("/projects/{pid}/sources")
def source_create(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    ws.get_project(conn, pid)
    with Tx(conn):
        s = ev.create_source(conn, pid, body)
        if body.get("link_claim_id"):
            ev.link_evidence(conn, body["link_claim_id"], s["id"], body.get("link") or {})
    return ev.get_source(conn, s["id"])


@router.post("/projects/{pid}/sources/check-duplicates")
def source_dups(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return {"matches": ev.find_duplicates(conn, pid, body)}


@router.get("/sources/{sid}")
def source_get(sid: str, conn=Depends(get_conn)):
    return ev.get_source(conn, sid)


@router.patch("/sources/{sid}")
def source_update(sid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ev.update_source(conn, sid, body)


@router.delete("/sources/{sid}")
def source_delete(sid: str, request: Request, conn=Depends(get_conn)):
    ev.get_source(conn, sid)
    att.delete_for_owner(conn, request.app.state.settings.attachments_dir, "source", sid)
    ev.delete_source(conn, sid)
    return {"ok": True}


# ---------------------------------------------------------------- questions, tasks, bookmarks

@router.get("/projects/{pid}/questions")
def questions(pid: str, conn=Depends(get_conn)):
    return ws.list_questions(conn, pid)


@router.post("/projects/{pid}/questions")
def question_create(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.create_question(conn, pid, body)


@router.patch("/questions/{qid}")
def question_update(qid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.update_question(conn, qid, body)


@router.delete("/questions/{qid}")
def question_delete(qid: str, conn=Depends(get_conn)):
    ws.delete_question(conn, qid)
    return {"ok": True}


@router.get("/projects/{pid}/tasks")
def tasks(pid: str, conn=Depends(get_conn)):
    return ws.list_tasks(conn, pid)


@router.post("/projects/{pid}/tasks")
def task_create(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.create_task(conn, pid, body)


@router.patch("/tasks/{tid}")
def task_update(tid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.update_task(conn, tid, body)


@router.delete("/tasks/{tid}")
def task_delete(tid: str, conn=Depends(get_conn)):
    ws.delete_task(conn, tid)
    return {"ok": True}


@router.get("/projects/{pid}/bookmarks")
def bookmarks(pid: str, conn=Depends(get_conn)):
    return ws.list_bookmarks(conn, pid)


@router.post("/projects/{pid}/bookmarks/toggle")
def bookmark_toggle(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    d.get_collection(conn, body["collection_id"])
    return ws.toggle_bookmark(conn, pid, body["collection_id"], body.get("note"))


@router.post("/projects/{pid}/bookmarks")
def bookmark_link(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return ws.add_link_bookmark(conn, pid, body.get("url"), body.get("title"), body.get("note"))


@router.delete("/bookmarks/{bid}")
def bookmark_delete(bid: str, conn=Depends(get_conn)):
    conn.execute("DELETE FROM bookmarks WHERE id = ?", (bid,))
    return {"ok": True}


# ---------------------------------------------------------------- recommendations

@router.post("/projects/{pid}/recommendations")
def recommendations(pid: str, body: dict = Body(default={}), conn=Depends(get_conn)):
    prefs = st.get(conn, "research_prefs")
    prefs.update({k: v for k, v in (body.get("prefs") or {}).items() if k in ("access", "remote_only", "languages", "record_types")})
    return rec.recommend(conn, pid, person_id=body.get("person_id"), question_id=body.get("question_id"), prefs=prefs,
                         limit=int(body.get("limit") or 25))


# ---------------------------------------------------------------- research log

@router.get("/projects/{pid}/log")
def log(pid: str, person_id: str | None = None, outcome: str | None = None, conn=Depends(get_conn)):
    return rl.list_log(conn, pid, person_id=person_id, outcome=outcome)


@router.post("/projects/{pid}/log")
def log_create(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    ws.get_project(conn, pid)
    e = rl.create_entry(conn, pid, body)
    return {**e, "alternatives": _alternatives(conn, e)}


@router.patch("/log/{eid}")
def log_update(eid: str, body: dict = Body(...), conn=Depends(get_conn)):
    return rl.update_entry(conn, eid, body)


@router.delete("/log/{eid}")
def log_delete(eid: str, request: Request, conn=Depends(get_conn)):
    att.delete_for_owner(conn, request.app.state.settings.attachments_dir, "log", eid)
    rl.delete_entry(conn, eid)
    return {"ok": True}


@router.get("/log/{eid}/alternatives")
def log_alternatives(eid: str, conn=Depends(get_conn)):
    return _alternatives(conn, rl.get_entry(conn, eid))


def _alternatives(conn, entry: dict) -> list[dict]:
    if entry["outcome"] not in ("no_result", "records_unavailable", "inaccessible"):
        return []
    person = ws.get_person(conn, entry["person_id"]) if entry.get("person_id") else None
    question = ws.get_question(conn, entry["question_id"]) if entry.get("question_id") else None
    windows = rec.research_windows(person, question)
    by_id = {c["id"]: c for c in d.all_collections(conn)}
    return rec.alternatives_for_entry(conn, entry, person, windows, by_id)


@router.get("/projects/{pid}/log.csv")
def log_csv(pid: str, conn=Depends(get_conn)):
    return Response(port.log_csv(conn, pid), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="kindred-research-log-{today_iso()}.csv"'})


# ---------------------------------------------------------------- attachments

@router.post("/projects/{pid}/attachments")
async def attachment_upload(pid: str, request: Request, owner_type: str = Form(...), owner_id: str = Form(...),
                            file: UploadFile = File(...)):
    data = await file.read(att.MAX_BYTES + 1)
    from .db import connect
    conn = connect(request.app.state.settings.db_path)
    try:
        return att.save(conn, request.app.state.settings.attachments_dir, pid, owner_type, owner_id, file.filename or "file", data)
    finally:
        conn.close()


@router.get("/attachments/{aid}/download")
def attachment_download(aid: str, request: Request, conn=Depends(get_conn)):
    a = att.get(conn, aid)
    p = att.path_for(request.app.state.settings.attachments_dir, a)
    if not p.exists():
        raise d.NotFound("attachment file")
    return FileResponse(p, media_type=a["mime_type"], filename=a["original_name"], content_disposition_type="attachment")


@router.delete("/attachments/{aid}")
def attachment_delete(aid: str, request: Request, conn=Depends(get_conn)):
    att.delete(conn, request.app.state.settings.attachments_dir, aid)
    return {"ok": True}


# ---------------------------------------------------------------- export / import / backup

@router.get("/export/full.json")
def export_full(conn=Depends(get_conn)):
    return JSONResponse(port.export_all(conn), headers={"Content-Disposition": f'attachment; filename="kindred-export-{today_iso()}.json"'})


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise d.ValidationError("File is too large")
    return data


def _parse_json(data: bytes) -> dict:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise d.ValidationError("File is not valid JSON")


@router.post("/import/full")
async def import_full(request: Request, file: UploadFile = File(...), confirm: str = Form("")):
    if confirm != "REPLACE":
        raise d.ValidationError("Type REPLACE to confirm replacing all data")
    doc = _parse_json(await _read_upload(file))
    port.validate_export(doc)
    safety = port.create_backup(request.app.state.settings, "pre-import")
    from .db import connect
    conn = connect(request.app.state.settings.db_path)
    try:
        counts = port.import_all(conn, doc)
    finally:
        conn.close()
    return {"imported": counts, "safety_backup": safety.name}


@router.get("/projects/{pid}/export.json")
def export_project(pid: str, request: Request, include_attachments: bool = True, conn=Depends(get_conn)):
    doc = port.export_project(conn, pid, request.app.state.settings.attachments_dir, include_attachments)
    safe = "".join(ch if ch.isalnum() else "-" for ch in doc["project"]["name"])[:40]
    return JSONResponse(doc, headers={"Content-Disposition": f'attachment; filename="kindred-project-{safe}-{today_iso()}.json"'})


@router.post("/import/project")
async def import_project(request: Request, file: UploadFile = File(...), rename: str = Form("")):
    doc = _parse_json(await _read_upload(file))
    from .db import connect
    conn = connect(request.app.state.settings.db_path)
    try:
        return port.import_project(conn, doc, request.app.state.settings.attachments_dir, rename or None)
    finally:
        conn.close()


@router.get("/backups")
def backups(request: Request):
    return port.list_backups(request.app.state.settings)


@router.post("/backups")
def backup_create(request: Request):
    p = port.create_backup(request.app.state.settings, "manual")
    return {"name": p.name, "size_bytes": p.stat().st_size, "path": str(p)}


def _backup_path(request: Request, name: str) -> Path:
    s = request.app.state.settings
    p = (s.backups_dir / name).resolve()
    if p.parent != s.backups_dir.resolve() or not p.name.endswith(".zip") or not p.exists():
        raise d.NotFound("backup")
    return p


@router.get("/backups/{name}/download")
def backup_download(name: str, request: Request):
    return FileResponse(_backup_path(request, name), media_type="application/zip", filename=name, content_disposition_type="attachment")


@router.post("/backups/restore")
async def backup_restore(request: Request, file: UploadFile | None = File(None), name: str = Form(""), confirm: str = Form("")):
    if confirm != "RESTORE":
        raise d.ValidationError("Type RESTORE to confirm replacing current data with the backup")
    s = request.app.state.settings
    if file is not None and file.filename:
        data = await _read_upload(file)
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(data)
            path = Path(tmp.name)
        try:
            return port.restore_backup(s, path)
        finally:
            path.unlink(missing_ok=True)
    return port.restore_backup(s, _backup_path(request, name))
