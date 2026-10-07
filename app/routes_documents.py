"""Imported documents: upload (drag and drop), recognised text, discovery, attach to people."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import FileResponse

from . import attachments as att, documents as docs
from .deps import get_conn
from .directory import NotFound, ValidationError

router = APIRouter()
MAX_FILES = 50


@router.post("/projects/{pid}/documents")
async def upload(pid: str, request: Request):
    form = await request.form(max_files=MAX_FILES, max_fields=MAX_FILES + 10)
    files = [u for u in form.getlist("files") if getattr(u, "filename", None)]
    if not files:
        raise ValidationError("Choose or drop at least one file")
    person_id = form.get("person_id") or None
    from .db import connect
    settings = request.app.state.settings
    conn = connect(settings.db_path)
    out, errors = [], []
    try:
        for up in files:
            data = await up.read()
            try:
                d = docs.add(conn, settings, pid, up.filename, data, person_id)
                out.append(d)
            except (ValidationError, NotFound) as e:
                errors.append({"file": up.filename, "error": str(e)})
    finally:
        conn.close()
    for d in out:
        docs.start_processing(settings, d["id"])
    return {"documents": out, "errors": errors}


@router.get("/projects/{pid}/documents")
def list_documents(pid: str, status: str | None = None, person_id: str | None = None, conn=Depends(get_conn)):
    return docs.list_docs(conn, pid, status, person_id)


@router.get("/documents/{did}")
def get_document(did: str, conn=Depends(get_conn)):
    return docs.get(conn, did)


@router.patch("/documents/{did}")
def patch_document(did: str, body: dict = Body(...), conn=Depends(get_conn)):
    return docs.update_doc(conn, did, body)


@router.post("/documents/{did}/reprocess")
def reprocess(did: str, request: Request, conn=Depends(get_conn)):
    docs.get(conn, did)
    conn.execute("UPDATE documents SET status = CASE WHEN status = 'attached' THEN status ELSE 'processing' END, transcription = NULL WHERE id = ?", (did,))
    docs.start_processing(request.app.state.settings, did)
    return docs.get(conn, did)


@router.get("/documents/{did}/page/{n}")
def page_preview(did: str, n: int, request: Request, conn=Depends(get_conn)):
    d = docs.get(conn, did)
    p = docs.preview_path(request.app.state.settings, d, n)
    if not p.exists():
        raise NotFound("page preview")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/documents/{did}/file")
def original_file(did: str, request: Request, conn=Depends(get_conn)):
    d = docs.get(conn, did)
    a = att.get(conn, d["attachment_id"])
    p = att.path_for(request.app.state.settings.attachments_dir, a)
    return FileResponse(p, media_type=a["mime_type"], filename=a["original_name"], content_disposition_type="inline")


@router.get("/documents/{did}/attach-preview")
def attach_preview(did: str, person_id: str, conn=Depends(get_conn)):
    return docs.preview_attach(conn, did, person_id)


@router.post("/documents/{did}/attach")
def attach(did: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    return docs.attach(conn, request.app.state.settings, did, body)


@router.delete("/documents/{did}")
def delete(did: str, request: Request, conn=Depends(get_conn)):
    docs.delete(conn, request.app.state.settings, did)
    return {"ok": True}


@router.post("/documents/{did}/ai/apply")
def ai_apply(did: str, conn=Depends(get_conn)):
    return docs.apply_ai(conn, did)
