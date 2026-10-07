"""Local attachments with persistent references.

Files are stored under <data_dir>/attachments/<project_id>/<attachment_id><ext>.
The original filename is kept only as metadata (sanitised); the stored name is
generated, so user-supplied names can never escape the folder. Active content
types (HTML, SVG, scripts) are refused, and downloads are always served as
attachments with nosniff.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .db import insert, new_id, now_iso, one, rows
from .directory import NotFound, ValidationError

MAX_BYTES = 50 * 1024 * 1024
ALLOWED = {
    ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff", ".txt": "text/plain", ".md": "text/markdown",
    ".csv": "text/csv", ".ged": "text/plain", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text", ".bmp": "image/bmp", ".heic": "image/heic",
    ".rtf": "application/rtf", ".mp4": "video/mp4", ".mov": "video/quicktime", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav",
}
OWNER_TABLES = {"source": "sources", "log": "research_log", "person": "persons", "document": "documents"}

# Leading bytes for formats where a mismatch would be suspicious.
MAGIC = {".pdf": [b"%PDF"], ".png": [b"\x89PNG"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"], ".gif": [b"GIF8"],
         ".tif": [b"II*\x00", b"MM\x00*"], ".tiff": [b"II*\x00", b"MM\x00*"], ".docx": [b"PK"], ".odt": [b"PK"]}


def safe_name(name: str) -> str:
    name = Path(name or "file").name
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip(" .") or "file"
    return name[:120]


def save(conn, attachments_dir: Path, project_id: str, owner_type: str, owner_id: str, filename: str, data: bytes) -> dict:
    if owner_type not in OWNER_TABLES:
        raise ValidationError("Attachments can belong to a source, a log entry, a person, or an imported document")
    owner = one(conn, f"SELECT id, project_id FROM {OWNER_TABLES[owner_type]} WHERE id = ?", (owner_id,))
    if not owner or owner["project_id"] != project_id:
        raise NotFound(owner_type)
    if len(data) == 0:
        raise ValidationError("The file is empty")
    if len(data) > MAX_BYTES:
        raise ValidationError(f"Files are limited to {MAX_BYTES // (1024 * 1024)} MB")
    clean = safe_name(filename)
    ext = Path(clean).suffix.lower()
    if ext not in ALLOWED:
        raise ValidationError(f"File type {ext or '(none)'} is not accepted. Allowed: {', '.join(sorted(ALLOWED))}")
    if ext in MAGIC and not any(data.startswith(m) for m in MAGIC[ext]):
        raise ValidationError(f"The file content does not look like a {ext} file")
    if ext in (".txt", ".md", ".csv", ".ged"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                data.decode("latin-1")
            except UnicodeDecodeError:
                raise ValidationError("Text files must be UTF-8 or Latin-1")
    aid = new_id()
    rel = f"{project_id}/{aid}{ext}"
    dest = attachments_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    insert(conn, "attachments", {"id": aid, "project_id": project_id, "owner_type": owner_type, "owner_id": owner_id,
                                 "original_name": clean, "stored_path": rel, "mime_type": ALLOWED[ext], "size_bytes": len(data),
                                 "sha256": sha, "created_at": now_iso()})
    return get(conn, aid)


def get(conn, aid: str) -> dict:
    a = one(conn, "SELECT * FROM attachments WHERE id = ?", (aid,))
    if not a:
        raise NotFound("attachment")
    return a


def path_for(attachments_dir: Path, a: dict) -> Path:
    p = (attachments_dir / a["stored_path"]).resolve()
    if attachments_dir.resolve() not in p.parents:
        raise NotFound("attachment")
    return p


def delete(conn, attachments_dir: Path, aid: str) -> None:
    a = get(conn, aid)
    p = path_for(attachments_dir, a)
    conn.execute("DELETE FROM attachments WHERE id = ?", (aid,))
    # an imported document and the source made from it share one file
    still_used = conn.execute("SELECT 1 FROM attachments WHERE stored_path = ? LIMIT 1", (a["stored_path"],)).fetchone()
    if p.exists() and not still_used:
        p.unlink()


def list_for(conn, owner_type: str, owner_id: str) -> list[dict]:
    return rows(conn, "SELECT * FROM attachments WHERE owner_type = ? AND owner_id = ? ORDER BY created_at", (owner_type, owner_id))


def delete_for_owner(conn, attachments_dir: Path, owner_type: str, owner_id: str) -> int:
    """Remove attachment rows and files belonging to a record that is being deleted."""
    items = list_for(conn, owner_type, owner_id)
    for a in items:
        delete(conn, attachments_dir, a["id"])
    return len(items)


def delete_for_project(conn, attachments_dir: Path, project_id: str) -> None:
    import shutil
    conn.execute("DELETE FROM attachments WHERE project_id = ?", (project_id,))
    folder = (attachments_dir / project_id).resolve()
    if attachments_dir.resolve() in folder.parents and folder.exists():
        shutil.rmtree(folder)
