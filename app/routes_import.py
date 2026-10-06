"""GEDCOM / Ancestry import endpoints."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

from .db import connect, today_iso
from .deps import get_conn
from .directory import ValidationError
from .gedcom import importer as imp
from .gedcom import media as md

router = APIRouter()
MAX_GEDCOM_BYTES = 500 * 1024 * 1024
MAX_UPLOAD_FILES = 60_000


async def _save_upload(up, tmpdir: Path, limit: int | None = None) -> Path:
    dest = tmpdir / f"u{len(list(tmpdir.iterdir()))}"
    size = 0
    with open(dest, "wb") as out:
        while True:
            chunk = await up.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if limit and size > limit:
                raise ValidationError("File is too large")
            out.write(chunk)
    return dest


async def _read_form(request: Request):
    return await request.form(max_files=MAX_UPLOAD_FILES, max_fields=MAX_UPLOAD_FILES + 50)


async def _media_from_form(form, tmpdir: Path) -> list[tuple[str, Path]]:
    out = []
    files = [u for u in form.getlist("media") if getattr(u, "filename", None)]
    paths = form.getlist("media_path")   # relative paths (folder uploads), in the same order as the files
    for i, up in enumerate(files):
        rel = paths[i] if len(paths) == len(files) and paths[i] else up.filename
        out.append((str(rel), await _save_upload(up, tmpdir)))
    return out


@router.post("")
async def create_import(request: Request):
    form = await _read_form(request)
    up = form.get("gedcom")
    if up is None or not getattr(up, "filename", None):
        raise ValidationError("Choose a GEDCOM file to import")
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        gpath = await _save_upload(up, tmpdir, MAX_GEDCOM_BYTES * 8 if up.filename.lower().endswith((".zip", ".gdz")) else MAX_GEDCOM_BYTES)
        media = await _media_from_form(form, tmpdir)
        conn = connect(request.app.state.settings.db_path)
        try:
            return imp.stage(conn, request.app.state.settings, gpath, up.filename, media, form.get("lineage_id") or None,
                             (form.get("project_name") or "").strip() or None, form.get("member") or None)
        except md.ArchiveError as e:
            raise ValidationError(str(e))
        finally:
            conn.close()


@router.get("")
def list_imports(conn=Depends(get_conn)):
    return {"imports": imp.list_batches(conn), "lineages": imp.lineages(conn), "snapshot_note": imp.SNAPSHOT_NOTE}


@router.get("/{batch_id}")
def get_import(batch_id: str, conn=Depends(get_conn)):
    return imp.get_batch(conn, batch_id)


@router.post("/{batch_id}/media")
async def add_media(batch_id: str, request: Request):
    form = await _read_form(request)
    with tempfile.TemporaryDirectory() as tmp:
        media = await _media_from_form(form, Path(tmp))
        if not media:
            raise ValidationError("Choose a media folder or ZIP")
        conn = connect(request.app.state.settings.db_path)
        try:
            return imp.add_media(conn, request.app.state.settings, batch_id, media)
        finally:
            conn.close()


@router.post("/{batch_id}/lineage")
def set_lineage(batch_id: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    b = imp.get_batch_row(conn, batch_id)
    if b["status"] != "previewed":
        raise ValidationError("Already committed")
    lin = body.get("lineage_id") or None
    if lin:
        imp.one_or_404(conn, "SELECT * FROM import_lineages WHERE id = ?", lin, "earlier import")
    conn.execute("UPDATE import_batches SET lineage_id = ? WHERE id = ?", (lin, batch_id))
    return imp.replan(conn, request.app.state.settings, batch_id)


@router.post("/{batch_id}/member")
def set_member(batch_id: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    """Choose which GEDCOM inside an uploaded archive to import."""
    b = imp.get_batch_row(conn, batch_id)
    if b["status"] != "previewed":
        raise ValidationError("Already committed")
    member = body.get("member")
    if member not in (b["media"] or {}).get("gedcom_archive_members", []):
        raise ValidationError("That file is not in the uploaded archive")
    conn.execute("UPDATE import_batches SET gedcom_member = ? WHERE id = ?", (member, batch_id))
    return imp.replan(conn, request.app.state.settings, batch_id)


@router.post("/{batch_id}/commit")
def commit(batch_id: str, request: Request, conn=Depends(get_conn)):
    return imp.commit(conn, request.app.state.settings, batch_id)


@router.post("/{batch_id}/undo")
def undo(batch_id: str, request: Request, conn=Depends(get_conn)):
    return imp.undo(conn, request.app.state.settings, batch_id)


@router.post("/{batch_id}/discard")
def discard(batch_id: str, request: Request, conn=Depends(get_conn)):
    imp.discard(conn, request.app.state.settings, batch_id)
    return {"ok": True}


@router.post("/{batch_id}/checked")
def checked(batch_id: str, body: dict = Body(...), conn=Depends(get_conn)):
    return imp.mark_checked(conn, batch_id, bool(body.get("checked")))


@router.get("/{batch_id}/report.json")
def report(batch_id: str, conn=Depends(get_conn)):
    b = imp.get_batch(conn, batch_id)
    doc = {"import_id": b["id"], "file": b["original_filename"], "sha256": b["sha256"], "status": b["status"], "product": b["product"],
           "gedcom_version": b["gedcom_version"], "encoding": b["encoding"], "committed_at": b["committed_at"], "preview": b["plan"],
           "report": b["report"], "review": b["review"]}
    return JSONResponse(doc, headers={"Content-Disposition": f'attachment; filename="import-report-{today_iso()}.json"'})


@router.get("/{batch_id}/original")
def original(batch_id: str, request: Request, conn=Depends(get_conn)):
    b = imp.get_batch_row(conn, batch_id)
    p = imp.imports_dir(request.app.state.settings) / b["stored_dir"] / "original" / b["original_filename"]
    if not p.exists():
        raise ValidationError("The original file is no longer stored")
    return FileResponse(p, filename=b["original_filename"], media_type="application/octet-stream", content_disposition_type="attachment")


@router.post("/review/{item_id}/decide")
def decide(item_id: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    return imp.decide_review(conn, request.app.state.settings, item_id, bool(body.get("accept")), body.get("choice"))


@router.get("/provenance/person/{person_id}")
def person_provenance(person_id: str, conn=Depends(get_conn)):
    return imp.person_provenance(conn, person_id)
