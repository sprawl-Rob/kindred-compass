"""Research log: every search, including searches that found nothing."""
from __future__ import annotations

from .db import insert, new_id, now_iso, one, rows, today_iso, update
from .directory import NotFound, ValidationError
from .taxonomy import LOG_OUTCOMES
from .workspace import _clean, touch

LOG_FIELDS = ["person_id", "question_id", "collection_id", "resource_text", "query_text", "filters_text", "year_from", "year_to",
              "place_text", "searched_on", "coverage_notes", "access_notes", "outcome", "result_url", "citation_text", "notes"]


def _select(where: str) -> str:
    return f"""SELECT l.*, c.name AS collection_name, pr.name AS provider_name, p.display_name AS person_name,
                      q.question AS question_text
               FROM research_log l LEFT JOIN collections c ON c.id = l.collection_id
               LEFT JOIN providers pr ON pr.id = c.provider_id LEFT JOIN persons p ON p.id = l.person_id
               LEFT JOIN research_questions q ON q.id = l.question_id WHERE {where}"""


def list_log(conn, project_id, person_id=None, collection_id=None, outcome=None) -> list[dict]:
    where, params = ["l.project_id = ?"], [project_id]
    for col, val in (("l.person_id", person_id), ("l.collection_id", collection_id), ("l.outcome", outcome)):
        if val:
            where.append(f"{col} = ?")
            params.append(val)
    out = rows(conn, _select(" AND ".join(where)) + " ORDER BY l.searched_on DESC, l.created_at DESC", params)
    for e in out:
        e["attachments"] = rows(conn, "SELECT id, original_name, mime_type, size_bytes FROM attachments WHERE owner_type='log' AND owner_id = ?", (e["id"],))
    return out


def get_entry(conn, eid) -> dict:
    e = one(conn, _select("l.id = ?"), (eid,))
    if not e:
        raise NotFound("log entry")
    return e


def _values(data: dict) -> dict:
    v = _clean(data, LOG_FIELDS)
    if "name_variants" in data:
        variants = [str(x).strip() for x in data.get("name_variants") or [] if str(x).strip()]
        import json
        v["name_variants_json"] = json.dumps(variants, ensure_ascii=False)
    if v.get("outcome") is not None and v["outcome"] not in LOG_OUTCOMES:
        raise ValidationError("Unknown outcome")
    for k in ("year_from", "year_to"):
        if v.get(k) is not None:
            v[k] = int(v[k])
    if v.get("result_url") and not v["result_url"].startswith(("http://", "https://")):
        raise ValidationError("Result URL must start with http:// or https://")
    return v


def create_entry(conn, project_id, data) -> dict:
    v = _values(data)
    if not v.get("outcome"):
        raise ValidationError("Choose an outcome")
    if not (v.get("collection_id") or v.get("resource_text")):
        raise ValidationError("Say which resource you searched")
    v.setdefault("searched_on", today_iso())
    v.setdefault("query_text", "")
    eid, ts = new_id(), now_iso()
    insert(conn, "research_log", {"id": eid, "project_id": project_id, **v, "created_at": ts, "updated_at": ts})
    touch(conn, project_id)
    return get_entry(conn, eid)


def update_entry(conn, eid, data) -> dict:
    get_entry(conn, eid)
    update(conn, "research_log", eid, {**_values(data), "updated_at": now_iso()})
    return get_entry(conn, eid)


def delete_entry(conn, eid) -> None:
    conn.execute("DELETE FROM research_log WHERE id = ?", (eid,))


def search_status(log_entries: list[dict], collection_id: str) -> dict:
    """Distinguish not searched / searched with no result / records unavailable / found something."""
    mine = [e for e in log_entries if e.get("collection_id") == collection_id]
    if not mine:
        return {"state": "not_searched", "label": "Not searched yet", "entries": []}
    latest = mine[0]
    o = latest["outcome"]
    state = {"no_result": "searched_no_result", "records_unavailable": "records_unavailable", "inaccessible": "inaccessible",
             "useful": "found", "possible_match": "possible_match", "follow_up": "follow_up"}[o]
    return {"state": state, "label": LOG_OUTCOMES[o], "last_searched": latest["searched_on"], "count": len(mine),
            "entries": [e.get("id") for e in mine]}
