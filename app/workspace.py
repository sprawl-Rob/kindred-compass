"""Research workspace: projects, places, people, names, claims, questions, tasks, bookmarks."""
from __future__ import annotations

from .dates import overlaps, parse_date
from .db import Tx, insert, new_id, now_iso, one, rows, update
from .directory import NotFound, ValidationError
from .taxonomy import (CLAIM_STATUSES, CLAIM_TYPES, CLUE_ONLY_FORMATS, DATE_QUALIFIERS, NAME_TYPES,
                       QUESTION_TYPES, RELATIONSHIP_TYPES)

MAX_TEXT = 20_000


def _clean(data: dict, allowed: list[str]) -> dict:
    out = {}
    for k in allowed:
        if k in data:
            v = data[k]
            if isinstance(v, str):
                v = v.strip()
                if len(v) > MAX_TEXT:
                    raise ValidationError(f"{k} is too long")
                v = v or None
            out[k] = v
    return out


def _require(cond, msg):
    if not cond:
        raise ValidationError(msg)


def _get(conn, table, rid, label):
    r = one(conn, f"SELECT * FROM {table} WHERE id = ?", (rid,))
    if not r:
        raise NotFound(label)
    return r


# ---------------------------------------------------------------- projects

def list_projects(conn) -> list[dict]:
    return rows(conn, """SELECT p.*, (SELECT COUNT(*) FROM persons WHERE project_id = p.id) AS person_count,
                         (SELECT COUNT(*) FROM research_questions WHERE project_id = p.id AND status = 'open') AS open_questions
                         FROM projects p ORDER BY p.is_demo, p.updated_at DESC""")


def create_project(conn, data: dict) -> dict:
    v = _clean(data, ["name", "description"])
    _require(v.get("name"), "Project name is required")
    pid, ts = data.get("id") or new_id(), now_iso()
    insert(conn, "projects", {"id": pid, **v, "is_demo": int(bool(data.get("is_demo"))), "created_at": ts, "updated_at": ts})
    return get_project(conn, pid)


def get_project(conn, pid) -> dict:
    return _get(conn, "projects", pid, "project")


def update_project(conn, pid, data) -> dict:
    get_project(conn, pid)
    v = _clean(data, ["name", "description"])
    update(conn, "projects", pid, {**v, "updated_at": now_iso()})
    return get_project(conn, pid)


def delete_project(conn, pid) -> None:
    get_project(conn, pid)
    with Tx(conn):
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))


def touch(conn, project_id):
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now_iso(), project_id))


# ---------------------------------------------------------------- places

PLACE_FIELDS = ["name", "country", "region", "county", "municipality", "historical_jurisdiction", "jurisdiction_notes"]


def list_places(conn, project_id) -> list[dict]:
    return rows(conn, "SELECT * FROM places WHERE project_id = ? ORDER BY name COLLATE NOCASE", (project_id,))


def create_place(conn, project_id, data) -> dict:
    get_project(conn, project_id)
    v = _clean(data, PLACE_FIELDS)
    if not v.get("name"):
        v["name"] = ", ".join(x for x in [v.get("municipality"), v.get("county"), v.get("region"), v.get("country")] if x)
    _require(v.get("name"), "A place needs at least a name or a country/region")
    pid, ts = data.get("id") or new_id(), now_iso()
    insert(conn, "places", {"id": pid, "project_id": project_id, **v, "created_at": ts, "updated_at": ts})
    return _get(conn, "places", pid, "place")


def update_place(conn, place_id, data) -> dict:
    _get(conn, "places", place_id, "place")
    update(conn, "places", place_id, {**_clean(data, PLACE_FIELDS), "updated_at": now_iso()})
    return _get(conn, "places", place_id, "place")


def find_or_create_place(conn, project_id, data: dict | None) -> str | None:
    if not data:
        return None
    if data.get("id"):
        return data["id"]
    v = _clean(data, PLACE_FIELDS)
    if not any(v.values()):
        return None
    match = one(conn, """SELECT id FROM places WHERE project_id = ? AND IFNULL(country,'') = ? AND IFNULL(region,'') = ?
                         AND IFNULL(county,'') = ? AND IFNULL(municipality,'') = ? AND IFNULL(historical_jurisdiction,'') = ?""",
                (project_id, v.get("country") or "", v.get("region") or "", v.get("county") or "", v.get("municipality") or "",
                 v.get("historical_jurisdiction") or ""))
    if match:
        return match["id"]
    return create_place(conn, project_id, v)["id"]


# ---------------------------------------------------------------- persons

PERSON_FIELDS = ["display_name", "sex", "living_status", "notes"]


def list_persons(conn, project_id) -> list[dict]:
    people = rows(conn, "SELECT * FROM persons WHERE project_id = ? ORDER BY display_name COLLATE NOCASE", (project_id,))
    for p in people:
        p["summary"] = person_summary(conn, p["id"])
    return people


def create_person(conn, project_id, data) -> dict:
    get_project(conn, project_id)
    v = _clean(data, PERSON_FIELDS)
    names = data.get("names") or []
    if not v.get("display_name") and names:
        n = names[0]
        v["display_name"] = " ".join(x for x in [n.get("given"), n.get("surname")] if x) or n.get("full_text")
    _require(v.get("display_name"), "A person needs a name (even a partial one)")
    if v.get("living_status") and v["living_status"] not in ("living", "deceased", "unknown"):
        raise ValidationError("living_status must be living, deceased, or unknown")
    pid, ts = data.get("id") or new_id(), now_iso()
    with Tx(conn):
        insert(conn, "persons", {"id": pid, "project_id": project_id, **v,
                                 "is_private": 1 if data.get("is_private", True) else 0, "created_at": ts, "updated_at": ts})
        for n in names:
            add_name(conn, pid, n)
        for c in data.get("claims") or []:
            create_claim(conn, project_id, {**c, "person_id": pid})
        touch(conn, project_id)
    return get_person(conn, pid)


def get_person(conn, pid) -> dict:
    p = _get(conn, "persons", pid, "person")
    p["names"] = rows(conn, "SELECT * FROM person_names WHERE person_id = ? ORDER BY created_at", (pid,))
    p["claims"] = list_claims(conn, person_id=pid)
    p["conflicts"] = detect_conflicts(p["claims"])
    p["questions"] = rows(conn, "SELECT * FROM research_questions WHERE person_id = ? ORDER BY created_at", (pid,))
    p["relationships"] = [c for c in p["claims"] if c["claim_type"] == "relationship"]
    p["incoming_relationships"] = rows(conn, """SELECT c.*, pr.display_name AS person_name FROM claims c JOIN persons pr ON pr.id = c.person_id
                                               WHERE c.related_person_id = ? AND c.claim_type = 'relationship'""", (pid,))
    p["summary"] = person_summary(conn, pid, p["claims"])
    return p


def update_person(conn, pid, data) -> dict:
    cur = _get(conn, "persons", pid, "person")
    v = _clean(data, PERSON_FIELDS)
    if "is_private" in data:
        v["is_private"] = 1 if data["is_private"] else 0
    update(conn, "persons", pid, {**v, "updated_at": now_iso()})
    touch(conn, cur["project_id"])
    return get_person(conn, pid)


def delete_person(conn, pid) -> None:
    cur = _get(conn, "persons", pid, "person")
    conn.execute("DELETE FROM persons WHERE id = ?", (pid,))
    touch(conn, cur["project_id"])


def person_summary(conn, pid, claims: list[dict] | None = None) -> dict:
    claims = claims if claims is not None else list_claims(conn, person_id=pid)
    live = [c for c in claims if c["status"] != "rejected"]

    def first(*types):
        for t in types:
            for c in live:
                if c["claim_type"] == t:
                    return c
        return None
    b, d = first("birth", "baptism"), first("death", "burial")
    from . import placenorm
    places = []
    for c in live:
        if c.get("place_label"):
            short = placenorm.parse(c["place_label"]).short()
            if short and short not in places:
                places.append(short)
    return {"birth": b and (b.get("date_text") or ""), "death": d and (d.get("date_text") or ""), "places": places[:4]}


# ---------------------------------------------------------------- names

NAME_FIELDS = ["name_type", "given", "surname", "full_text", "script", "language", "note"]


def add_name(conn, person_id, data) -> dict:
    v = _clean(data, NAME_FIELDS)
    v.setdefault("name_type", "birth")
    if v["name_type"] not in NAME_TYPES:
        raise ValidationError("Unknown name type")
    _require(v.get("given") or v.get("surname") or v.get("full_text"), "A name needs a given name, surname, or full text")
    nid = new_id()
    insert(conn, "person_names", {"id": nid, "person_id": person_id, **v, "created_at": now_iso()})
    return one(conn, "SELECT * FROM person_names WHERE id = ?", (nid,))


def delete_name(conn, name_id) -> None:
    conn.execute("DELETE FROM person_names WHERE id = ?", (name_id,))


# ---------------------------------------------------------------- claims

CLAIM_FIELDS = ["claim_type", "date_text", "date_qualifier", "year_from", "year_to", "place_id", "to_place_id",
                "related_person_id", "relationship_type", "relationship_qualifier", "value_text", "statement", "status", "status_note"]


def _claim_select(where: str) -> str:
    return f"""SELECT c.*, pl.name AS place_label, pl.country AS place_country, pl.region AS place_region, pl.county AS place_county,
                      pl.municipality AS place_municipality, pl.historical_jurisdiction AS place_historical_jurisdiction,
                      tp.name AS to_place_label, rp.display_name AS related_person_name
               FROM claims c LEFT JOIN places pl ON pl.id = c.place_id LEFT JOIN places tp ON tp.id = c.to_place_id
               LEFT JOIN persons rp ON rp.id = c.related_person_id WHERE {where}"""


def list_claims(conn, person_id=None, project_id=None) -> list[dict]:
    if person_id:
        cl = rows(conn, _claim_select("c.person_id = ?") + " ORDER BY COALESCE(c.year_from, 9999), c.created_at", (person_id,))
    else:
        cl = rows(conn, _claim_select("c.project_id = ?") + " ORDER BY c.person_id, COALESCE(c.year_from, 9999)", (project_id,))
    for c in cl:
        c["evidence"] = claim_evidence(conn, c["id"])
        c["evidence_summary"] = evidence_summary(c)
    return cl


def get_claim(conn, cid) -> dict:
    c = one(conn, _claim_select("c.id = ?"), (cid,))
    if not c:
        raise NotFound("claim")
    c["evidence"] = claim_evidence(conn, cid)
    c["evidence_summary"] = evidence_summary(c)
    return c


def _claim_values(conn, project_id, data, existing=None) -> dict:
    v = _clean(data, CLAIM_FIELDS)
    if "place" in data:
        v["place_id"] = find_or_create_place(conn, project_id, data["place"])
    if "to_place" in data:
        v["to_place_id"] = find_or_create_place(conn, project_id, data["to_place"])
    ctype = v.get("claim_type") or (existing or {}).get("claim_type")
    _require(ctype in CLAIM_TYPES, "Unknown claim type")
    if "date_text" in v and ("year_from" not in data and "year_to" not in data):
        v.update(parse_date(v.get("date_text")))
    if v.get("date_qualifier") and v["date_qualifier"] not in DATE_QUALIFIERS:
        raise ValidationError("Unknown date qualifier")
    for k in ("year_from", "year_to"):
        if v.get(k) is not None:
            v[k] = int(v[k])
            _require(-1000 < v[k] < 2200, "Year out of range")
    if v.get("year_from") is not None and v.get("year_to") is not None:
        _require(v["year_from"] <= v["year_to"], "Year range is reversed")
    if v.get("status"):
        _require(v["status"] in CLAIM_STATUSES, "Unknown claim status")
    if ctype == "relationship":
        rel = v.get("relationship_type") or (existing or {}).get("relationship_type")
        _require(rel in RELATIONSHIP_TYPES, "A relationship claim needs a relationship type")
        _require(v.get("related_person_id") or (existing or {}).get("related_person_id") or v.get("value_text"),
                 "A relationship claim needs a related person (or a description)")
        # Relationships start tentative — never auto-confirmed.
        if not existing:
            v.setdefault("status", "tentative")
    return v


def create_claim(conn, project_id, data) -> dict:
    person = _get(conn, "persons", data.get("person_id"), "person")
    _require(person["project_id"] == project_id, "Person belongs to a different project")
    v = _claim_values(conn, project_id, data)
    if v.get("status") == "confirmed":
        raise ValidationError("A new claim cannot start as confirmed; link evidence first, then confirm it.")
    cid, ts = new_id(), now_iso()
    insert(conn, "claims", {"id": cid, "project_id": project_id, "person_id": person["id"], **v, "created_at": ts, "updated_at": ts})
    touch(conn, project_id)
    return get_claim(conn, cid)


def update_claim(conn, cid, data) -> dict:
    cur = get_claim(conn, cid)
    v = _claim_values(conn, cur["project_id"], data, existing=cur)
    if v.get("status") == "confirmed" and cur["status"] != "confirmed":
        check_can_confirm(cur, override_note=data.get("status_note"))
    update(conn, "claims", cid, {**v, "updated_at": now_iso()})
    touch(conn, cur["project_id"])
    return get_claim(conn, cid)


def delete_claim(conn, cid) -> None:
    cur = get_claim(conn, cid)
    conn.execute("DELETE FROM claims WHERE id = ?", (cid,))
    touch(conn, cur["project_id"])


def check_can_confirm(claim: dict, override_note: str | None = None) -> None:
    """Confirming requires supporting evidence; clue-only formats are not proof on their own."""
    s = claim["evidence_summary"]
    if s["supports"] == 0:
        raise ValidationError("Link at least one supporting source before marking this claim confirmed.")
    if s["supports_only_clue_formats"] and claim["claim_type"] == "relationship" and not override_note:
        raise ValidationError("This relationship is supported only by contributed trees or cemetery memorials, which are clues, not proof. "
                              "Add independent evidence, or record a note explaining your reasoning to confirm anyway.")


def claim_evidence(conn, claim_id) -> list[dict]:
    return rows(conn, """SELECT ce.*, s.title AS source_title, s.record_format, s.informant_knowledge, s.url AS source_url,
                         s.citation_text, s.repository FROM claim_evidence ce JOIN sources s ON s.id = ce.source_id
                         WHERE ce.claim_id = ? ORDER BY ce.created_at""", (claim_id,))


def evidence_summary(c: dict) -> dict:
    ev = c.get("evidence") or []
    sup = [e for e in ev if e["stance"] == "supports"]
    con = [e for e in ev if e["stance"] == "contradicts"]
    warnings = []
    clue_only = bool(sup) and all(e["record_format"] in CLUE_ONLY_FORMATS for e in sup)
    if clue_only:
        warnings.append("Supported only by contributed trees / cemetery memorials — treat as clues, not proof.")
    if con:
        warnings.append(f"{len(con)} source(s) contradict this claim.")
    if sup and all(e["identity_match"] in ("possible", "uncertain") for e in sup):
        warnings.append("Supporting records are not yet firmly identified as this person.")
    if not ev:
        warnings.append("No sources linked yet.")
    return {"supports": len(sup), "contradicts": len(con), "mentions": len(ev) - len(sup) - len(con),
            "supports_only_clue_formats": clue_only, "warnings": warnings}


SINGLE_EVENT_TYPES = {"birth", "baptism", "death", "burial"}


def detect_conflicts(claims: list[dict]) -> list[dict]:
    """Flag (never resolve) claims of single-occurrence events whose dates or places disagree."""
    out = []
    live = [c for c in claims if c["status"] != "rejected"]
    by_type: dict[str, list] = {}
    for c in live:
        if c["claim_type"] in SINGLE_EVENT_TYPES:
            by_type.setdefault(c["claim_type"], []).append(c)
    for t, cs in by_type.items():
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                a, b = cs[i], cs[j]
                reasons = []
                if not overlaps(a.get("year_from"), a.get("year_to"), b.get("year_from"), b.get("year_to")):
                    reasons.append(f"dates differ ({a.get('date_text') or '?'} vs {b.get('date_text') or '?'})")
                if a.get("place_id") and b.get("place_id") and a["place_id"] != b["place_id"]:
                    pa, pb = (a.get("place_label") or "").lower(), (b.get("place_label") or "").lower()
                    if pa and pb and pa not in pb and pb not in pa:
                        reasons.append(f"places differ ({a.get('place_label')} vs {b.get('place_label')})")
                if reasons:
                    out.append({"claim_type": t, "claim_ids": [a["id"], b["id"]], "reason": "; ".join(reasons)})
    # Relationship conflicts: more than two different parent claims of the same kind
    parents = [c for c in live if c["claim_type"] == "relationship" and c.get("relationship_type") == "child" and c.get("related_person_id")
               and (c.get("relationship_qualifier") or "biological") in ("biological", "unknown")]
    distinct = {c["related_person_id"] for c in parents}
    if len(distinct) > 2:
        out.append({"claim_type": "relationship", "claim_ids": [c["id"] for c in parents],
                    "reason": f"{len(distinct)} different people are proposed as biological (or unstated) parents"})
    return out


# ---------------------------------------------------------------- questions

QUESTION_FIELDS = ["person_id", "question", "question_type", "year_from", "year_to", "place_id", "status", "notes"]


def list_questions(conn, project_id) -> list[dict]:
    return rows(conn, """SELECT q.*, p.display_name AS person_name, pl.name AS place_label FROM research_questions q
                         LEFT JOIN persons p ON p.id = q.person_id LEFT JOIN places pl ON pl.id = q.place_id
                         WHERE q.project_id = ? ORDER BY q.status, q.created_at DESC""", (project_id,))


def get_question(conn, qid) -> dict:
    q = one(conn, """SELECT q.*, p.display_name AS person_name, pl.name AS place_label, pl.country AS place_country,
                     pl.region AS place_region, pl.county AS place_county, pl.municipality AS place_municipality,
                     pl.historical_jurisdiction AS place_historical_jurisdiction
                     FROM research_questions q LEFT JOIN persons p ON p.id = q.person_id
                     LEFT JOIN places pl ON pl.id = q.place_id WHERE q.id = ?""", (qid,))
    if not q:
        raise NotFound("question")
    return q


def _question_values(conn, project_id, data) -> dict:
    v = _clean(data, QUESTION_FIELDS)
    if "place" in data:
        v["place_id"] = find_or_create_place(conn, project_id, data["place"])
    if v.get("question_type"):
        _require(v["question_type"] in QUESTION_TYPES, "Unknown question type")
    if v.get("status"):
        _require(v["status"] in ("open", "answered", "on_hold"), "Unknown status")
    for k in ("year_from", "year_to"):
        if v.get(k) is not None:
            v[k] = int(v[k])
    if v.get("year_from") is not None and v.get("year_to") is not None:
        _require(v["year_from"] <= v["year_to"], "Year range is reversed")
    return v


def create_question(conn, project_id, data) -> dict:
    get_project(conn, project_id)
    v = _question_values(conn, project_id, data)
    _require(v.get("question"), "Write the research question")
    v.setdefault("question_type", "other")
    qid, ts = new_id(), now_iso()
    insert(conn, "research_questions", {"id": qid, "project_id": project_id, **v, "created_at": ts, "updated_at": ts})
    touch(conn, project_id)
    return get_question(conn, qid)


def update_question(conn, qid, data) -> dict:
    cur = get_question(conn, qid)
    update(conn, "research_questions", qid, {**_question_values(conn, cur["project_id"], data), "updated_at": now_iso()})
    return get_question(conn, qid)


def delete_question(conn, qid) -> None:
    get_question(conn, qid)
    conn.execute("DELETE FROM research_questions WHERE id = ?", (qid,))


# ---------------------------------------------------------------- tasks & bookmarks

TASK_FIELDS = ["question_id", "person_id", "collection_id", "title", "status", "notes", "origin"]


def list_tasks(conn, project_id) -> list[dict]:
    return rows(conn, """SELECT t.*, c.name AS collection_name, p.display_name AS person_name FROM tasks t
                         LEFT JOIN collections c ON c.id = t.collection_id LEFT JOIN persons p ON p.id = t.person_id
                         WHERE t.project_id = ? ORDER BY t.status DESC, t.created_at DESC""", (project_id,))


def create_task(conn, project_id, data) -> dict:
    get_project(conn, project_id)
    v = _clean(data, TASK_FIELDS)
    _require(v.get("title"), "A task needs a title")
    tid, ts = new_id(), now_iso()
    insert(conn, "tasks", {"id": tid, "project_id": project_id, **v, "created_at": ts, "updated_at": ts})
    return one(conn, "SELECT * FROM tasks WHERE id = ?", (tid,))


def update_task(conn, tid, data) -> dict:
    _get(conn, "tasks", tid, "task")
    v = _clean(data, ["title", "status", "notes"])
    if v.get("status"):
        _require(v["status"] in ("todo", "done"), "Unknown task status")
    update(conn, "tasks", tid, {**v, "updated_at": now_iso()})
    return one(conn, "SELECT * FROM tasks WHERE id = ?", (tid,))


def delete_task(conn, tid) -> None:
    conn.execute("DELETE FROM tasks WHERE id = ?", (tid,))


def list_bookmarks(conn, project_id) -> list[dict]:
    return rows(conn, """SELECT b.*, c.name AS collection_name, p.name AS provider_name FROM bookmarks b
                         LEFT JOIN collections c ON c.id = b.collection_id LEFT JOIN providers p ON p.id = c.provider_id
                         WHERE b.project_id IS NULL OR b.project_id = ? ORDER BY b.created_at DESC""", (project_id,))


def toggle_bookmark(conn, project_id, collection_id, note=None) -> dict:
    existing = one(conn, "SELECT id FROM bookmarks WHERE collection_id = ? AND (project_id IS ? OR project_id = ?)",
                   (collection_id, project_id, project_id))
    if existing:
        conn.execute("DELETE FROM bookmarks WHERE id = ?", (existing["id"],))
        return {"saved": False}
    insert(conn, "bookmarks", {"id": new_id(), "project_id": project_id, "collection_id": collection_id, "note": note, "created_at": now_iso()})
    return {"saved": True}


def add_link_bookmark(conn, project_id, url, title, note=None) -> dict:
    _require(url and url.startswith(("http://", "https://")), "Bookmark URL must start with http:// or https://")
    bid = new_id()
    insert(conn, "bookmarks", {"id": bid, "project_id": project_id, "url": url, "title": title or url, "note": note, "created_at": now_iso()})
    return one(conn, "SELECT * FROM bookmarks WHERE id = ?", (bid,))
