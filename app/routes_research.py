"""Automatic research runs, archive integrations and their keys, and result review."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from . import settings_store as st
from .deps import get_conn
from .directory import NotFound, ValidationError
from .integrations import ADAPTERS
from .integrations.base import SearchQuery
from .research import engine as eng

router = APIRouter()


def _svc(request: Request) -> eng.ResearchService:
    return request.app.state.research


@router.get("/archives")
def archives(request: Request, conn=Depends(get_conn)):
    return eng.archive_status(request.app.state.creds, conn)


@router.put("/archives/{key}/key")
def archive_key(key: str, request: Request, body: dict = Body(...)):
    if key not in ADAPTERS or not (ADAPTERS[key].requires_key or ADAPTERS[key].optional_key):
        raise NotFound("archive that uses a key")
    k = (body.get("api_key") or "").strip()
    if len(k) < 6 or any(ch.isspace() for ch in k):
        raise ValidationError("That does not look like an API key")
    try:
        request.app.state.creds.set(eng.KEY_PREFIX + key, k)
    except RuntimeError as e:
        raise ValidationError(str(e))
    return {"ok": True}


@router.delete("/archives/{key}/key")
def archive_key_delete(key: str, request: Request):
    request.app.state.creds.delete(eng.KEY_PREFIX + key)
    return {"ok": True}


@router.patch("/archives/{key}")
def archive_toggle(key: str, body: dict = Body(...), conn=Depends(get_conn)):
    if key not in ADAPTERS:
        raise NotFound("archive")
    cur = st.get(conn, "archives") or {}
    cur[key] = bool(body.get("enabled", True))
    st.put(conn, "archives", cur)
    return {"ok": True}


@router.post("/archives/{key}/test")
def archive_test(key: str, request: Request):
    """One small live search to confirm the integration (and key) works."""
    a = eng.make_adapter(request.app.state.creds, key, blocking=False)
    a.check_key()
    res = a.search(SearchQuery(text="Smith", page_size=3))
    return {"ok": True, "detail": f"Connected. The archive returned {len(res.hits)} sample result(s)" +
            (f" of {res.total}" if res.total is not None else "") + "."}


@router.post("/projects/{pid}/research/plan")
def research_plan(pid: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    return eng.plan(conn, request.app.state.creds, pid, body.get("person_id"), body.get("question_id"),
                    {**eng.DEFAULTS, **(body.get("options") or {})})


@router.post("/projects/{pid}/research/runs")
async def research_start(pid: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    if not body.get("person_id"):
        raise ValidationError("Choose a person to research")
    return await _svc(request).start(conn, pid, body["person_id"], body.get("question_id"), body.get("options") or {})


@router.get("/projects/{pid}/research/runs")
def research_runs(pid: str, request: Request, person_id: str | None = None, conn=Depends(get_conn)):
    return _svc(request).list(conn, pid, person_id)


@router.get("/projects/{pid}/research/review")
def research_review(pid: str, conn=Depends(get_conn)):
    return eng.pending_review(conn, pid)


@router.get("/research/runs/{run_id}")
def research_get(run_id: str, request: Request, conn=Depends(get_conn)):
    return _svc(request).get(conn, run_id)


@router.post("/research/runs/{run_id}/cancel")
def research_cancel(run_id: str, request: Request, conn=Depends(get_conn)):
    if request.app.state.ai_research.is_running(run_id):
        return request.app.state.ai_research.cancel(conn, run_id)
    return _svc(request).cancel(conn, run_id)


@router.post("/research/hits/{hit_id}")
def research_decide(hit_id: str, body: dict = Body(...), conn=Depends(get_conn)):
    return eng.decide_hit(conn, hit_id, body.get("action"), body.get("claim_id"), body.get("stance"), body.get("identity"))



@router.post("/projects/{pid}/research/ai/preview")
def ai_research_preview(pid: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    if not body.get("person_id"):
        raise ValidationError("Choose a person to research")
    return request.app.state.ai_research.preview(conn, pid, body["person_id"], body.get("question_id"), body.get("options") or {}, body.get("override"))


@router.post("/projects/{pid}/research/ai/runs")
async def ai_research_start(pid: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    return await request.app.state.ai_research.start(conn, pid, body.get("person_id"), body.get("question_id"), body.get("options") or {},
                                                     body.get("override"), body.get("confirmed_model") or "")
