"""AI settings, model discovery, previews, runs, and proposal review."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from .ai.providers import PROVIDERS
from .deps import get_conn
from .directory import NotFound, ValidationError

router = APIRouter()


def _svc(request: Request):
    return request.app.state.ai


def _provider(p: str) -> str:
    if p not in PROVIDERS:
        raise NotFound("provider")
    return p


@router.get("/config")
def config(request: Request, conn=Depends(get_conn)):
    return _svc(request).get_config(conn)


@router.patch("/config")
def config_update(request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    return _svc(request).update_config(conn, body)


@router.post("/consent")
def consent(request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    return _svc(request).set_consent(conn, bool(body.get("acknowledge")), body.get("allow_possibly_living"), body.get("allow_attachments"))


@router.put("/keys/{provider}")
def key_set(provider: str, request: Request, body: dict = Body(...)):
    _svc(request).set_key(_provider(provider), body.get("api_key", ""))
    return {"ok": True}


@router.delete("/keys/{provider}")
def key_delete(provider: str, request: Request):
    _svc(request).delete_key(_provider(provider))
    return {"ok": True}


@router.get("/models/{provider}")
def models_cached(provider: str, request: Request, conn=Depends(get_conn)):
    return _svc(request).cached_models(conn, _provider(provider))


@router.post("/models/{provider}/refresh")
async def models_refresh(provider: str, request: Request):
    return await _svc(request).refresh_models(_provider(provider))


@router.post("/models/{provider}/validate")
async def models_validate(provider: str, request: Request, body: dict = Body(...)):
    return await _svc(request).validate_model(_provider(provider), body.get("model_id", ""))


@router.post("/test/{provider}")
async def test_connection(provider: str, request: Request):
    return await _svc(request).test_connection(_provider(provider))


@router.post("/test/{provider}/generate")
async def test_generate(provider: str, request: Request, body: dict = Body(...)):
    if not body.get("acknowledge_charges"):
        raise ValidationError("Confirm that this test may incur a small charge")
    return await _svc(request).test_generation(_provider(provider), body.get("model", ""))


@router.post("/preview")
def preview(request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    return _svc(request).preview(conn, body.get("task"), body.get("inputs") or {}, body.get("override"))


@router.post("/runs")
async def run_start(request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    return await _svc(request).start(conn, body.get("task"), body.get("inputs") or {}, body.get("override"), body.get("confirmed_model"))


@router.get("/runs")
def runs(request: Request, project_id: str | None = None, conn=Depends(get_conn)):
    return _svc(request).list_runs(conn, project_id)


@router.get("/runs/{run_id}")
def run_get(run_id: str, request: Request, conn=Depends(get_conn)):
    return _svc(request).get_run(conn, run_id)


@router.post("/runs/{run_id}/cancel")
def run_cancel(run_id: str, request: Request, conn=Depends(get_conn)):
    return _svc(request).cancel(conn, run_id)


@router.post("/proposals/{proposal_id}/decide")
def proposal_decide(proposal_id: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    return _svc(request).decide(conn, proposal_id, bool(body.get("accept")), body.get("edits"))
