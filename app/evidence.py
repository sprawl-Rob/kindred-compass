"""Sources, citations, and the links between claims and sources.

Leads (research log), assertions (claims) and evidence (sources + claim_evidence)
are kept distinct. Truth is never assigned from source format: format, informant
knowledge, identity match, and the researcher's assessment are recorded separately.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from .db import insert, new_id, now_iso, one, rows, update
from .directory import NotFound, ValidationError
from .taxonomy import ASSESSMENTS, IDENTITY_MATCH, INFORMANT_KNOWLEDGE, RECORD_FORMATS, STANCES
from .workspace import _clean, _get, touch

SOURCE_FIELDS = ["title", "creator", "repository", "collection_id", "collection_name", "record_date_text", "page_ref", "url",
                 "accessed_on", "transcription", "excerpt", "record_format", "informant", "informant_knowledge",
                 "citation_text", "research_log_id", "provenance_note"]


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/")
    return urlunsplit(("", host, path, p.query, "")).lstrip("/")


def _norm_text(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def fingerprint(s: dict) -> str:
    """Same record seen twice → same fingerprint. URL wins; else title+repository+page."""
    u = normalize_url(s.get("url"))
    if u:
        return "url:" + u
    return "txt:" + "|".join(_norm_text(s.get(k)) for k in ("title", "repository", "page_ref"))


def format_citation(s: dict) -> str:
    """A simple, consistent citation (layered: what, where-in, where-from, when-accessed)."""
    parts = []
    if s.get("creator"):
        parts.append(s["creator"])
    parts.append(f"“{s.get('title')}”" if s.get("title") else "Untitled record")
    if s.get("record_date_text"):
        parts.append(s["record_date_text"])
    if s.get("page_ref"):
        parts.append(s["page_ref"])
    where = ", ".join(x for x in [s.get("collection_name"), s.get("repository")] if x)
    if where:
        parts.append(where)
    if s.get("url"):
        parts.append(s["url"])
    if s.get("accessed_on"):
        parts.append(f"accessed {s['accessed_on']}")
    return "; ".join(parts) + "."


def _values(data: dict) -> dict:
    v = _clean(data, SOURCE_FIELDS)
    if v.get("record_format") and v["record_format"] not in RECORD_FORMATS:
        raise ValidationError("Unknown record format")
    if v.get("informant_knowledge") and v["informant_knowledge"] not in INFORMANT_KNOWLEDGE:
        raise ValidationError("Unknown informant knowledge value")
    if v.get("url") and not v["url"].startswith(("http://", "https://")):
        raise ValidationError("Source URL must start with http:// or https://")
    return v


def list_sources(conn, project_id) -> list[dict]:
    out = rows(conn, """SELECT s.*, c.name AS directory_collection_name,
                        (SELECT COUNT(*) FROM claim_evidence ce WHERE ce.source_id = s.id) AS claim_count
                        FROM sources s LEFT JOIN collections c ON c.id = s.collection_id
                        WHERE s.project_id = ? ORDER BY s.created_at DESC""", (project_id,))
    return out


def get_source(conn, sid) -> dict:
    s = one(conn, "SELECT * FROM sources WHERE id = ?", (sid,))
    if not s:
        raise NotFound("source")
    s["claims"] = rows(conn, """SELECT ce.*, c.claim_type, c.statement, c.date_text, c.status AS claim_status, p.display_name AS person_name
                                FROM claim_evidence ce JOIN claims c ON c.id = ce.claim_id JOIN persons p ON p.id = c.person_id
                                WHERE ce.source_id = ?""", (sid,))
    s["attachments"] = rows(conn, "SELECT id, original_name, mime_type, size_bytes, sha256, created_at FROM attachments "
                                  "WHERE owner_type = 'source' AND owner_id = ?", (sid,))
    s["possible_duplicates"] = find_duplicates(conn, s["project_id"], s, exclude_id=sid)
    return s


def find_duplicates(conn, project_id, data: dict, exclude_id: str | None = None) -> list[dict]:
    fp = fingerprint(data)
    if fp in ("txt:||", "url:"):
        return []
    return rows(conn, "SELECT id, title, repository, url, page_ref, created_at FROM sources WHERE project_id = ? AND fingerprint = ? AND id IS NOT ?",
                (project_id, fp, exclude_id))


def create_source(conn, project_id, data) -> dict:
    v = _values(data)
    if not v.get("title"):
        raise ValidationError("A source needs a title (what the record is)")
    v.setdefault("record_format", "unknown")
    v["fingerprint"] = fingerprint(v)
    dups = find_duplicates(conn, project_id, v)
    if dups and data.get("duplicate_of_id") is None and not data.get("allow_duplicate"):
        # Do not merge: tell the caller, who can link to the existing source or keep both.
        raise DuplicateSource(dups)
    if data.get("duplicate_of_id"):
        _get(conn, "sources", data["duplicate_of_id"], "source")
        v["duplicate_of_id"] = data["duplicate_of_id"]
    if not v.get("citation_text"):
        v["citation_text"] = format_citation(v)
    sid, ts = new_id(), now_iso()
    insert(conn, "sources", {"id": sid, "project_id": project_id, **v, "created_at": ts, "updated_at": ts})
    touch(conn, project_id)
    return get_source(conn, sid)


class DuplicateSource(Exception):
    def __init__(self, matches):
        super().__init__("possible duplicate")
        self.matches = matches


def update_source(conn, sid, data) -> dict:
    cur = get_source(conn, sid)
    v = _values(data)
    merged = {**cur, **v}
    v["fingerprint"] = fingerprint(merged)
    if data.get("regenerate_citation"):
        v["citation_text"] = format_citation(merged)
    update(conn, "sources", sid, {**v, "updated_at": now_iso()})
    return get_source(conn, sid)


def delete_source(conn, sid) -> None:
    get_source(conn, sid)
    conn.execute("DELETE FROM sources WHERE id = ?", (sid,))


# ---------------------------------------------------------------- claim ↔ source

LINK_FIELDS = ["stance", "identity_match", "assessment", "interpretation_note"]


def link_evidence(conn, claim_id, source_id, data) -> dict:
    claim = _get(conn, "claims", claim_id, "claim")
    src = _get(conn, "sources", source_id, "source")
    if claim["project_id"] != src["project_id"]:
        raise ValidationError("Claim and source belong to different projects")
    v = _clean(data, LINK_FIELDS)
    _check_link(v)
    existing = one(conn, "SELECT id FROM claim_evidence WHERE claim_id = ? AND source_id = ?", (claim_id, source_id))
    ts = now_iso()
    if existing:
        update(conn, "claim_evidence", existing["id"], {**v, "updated_at": ts})
        lid = existing["id"]
    else:
        lid = new_id()
        insert(conn, "claim_evidence", {"id": lid, "claim_id": claim_id, "source_id": source_id, **v, "created_at": ts, "updated_at": ts})
    touch(conn, claim["project_id"])
    return one(conn, "SELECT * FROM claim_evidence WHERE id = ?", (lid,))


def update_link(conn, link_id, data) -> dict:
    _get(conn, "claim_evidence", link_id, "evidence link")
    v = _clean(data, LINK_FIELDS)
    _check_link(v)
    update(conn, "claim_evidence", link_id, {**v, "updated_at": now_iso()})
    return one(conn, "SELECT * FROM claim_evidence WHERE id = ?", (link_id,))


def unlink(conn, link_id) -> None:
    conn.execute("DELETE FROM claim_evidence WHERE id = ?", (link_id,))


def _check_link(v):
    if v.get("stance") and v["stance"] not in STANCES:
        raise ValidationError("Unknown stance")
    if v.get("identity_match") and v["identity_match"] not in IDENTITY_MATCH:
        raise ValidationError("Unknown identity match value")
    if v.get("assessment") and v["assessment"] not in ASSESSMENTS:
        raise ValidationError("Unknown assessment")
