"""Family-centred views: tree, person overview with record checklist, and the 'what next' list."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from . import checklist, combine as cmb, family as fam, settings_store as st
from .db import rows
from .deps import get_conn
from .directory import NotFound, ValidationError
from .research import engine as eng

router = APIRouter()


def _root(conn, f: fam.Family, pid: str) -> str | None:
    roots = st.get(conn, "tree_roots") or {}
    r = roots.get(pid)
    return r if r in f.people else f.default_root()


def _node(f, pid, depth, seen=None, path=()):
    """Pedigree node. In a full tree the same ancestor can appear more than once (cousins married); the first
    appearance is expanded and later ones are marked as repeats, so the chart doesn't grow without end."""
    seen = seen if seen is not None else set()
    p = f.people[pid]
    parents = sorted(p.parents, key=lambda x: 0 if (f.people[x].sex or "").upper().startswith("M") else 1)
    repeat = pid in seen
    seen.add(pid)
    expand = depth > 0 and not repeat and pid not in path
    return {**f.summary(pid), "has_more": (not expand) and bool(p.parents), "repeat": repeat and bool(p.parents),
            "child_count": len(p.children),
            "parents": [_node(f, x, depth - 1, seen, path + (pid,)) for x in parents] if expand else []}


@router.get("/projects/{pid}/tree")
def tree(pid: str, root: str | None = None, depth: str = "3", conn=Depends(get_conn)):
    """depth = generations above the root person (0 = just the person), or "full" for every recorded generation."""
    f = fam.load(conn, pid)
    if not f.people:
        return {"root": None, "pedigree": None, "people": []}
    r = root if root in f.people else _root(conn, f, pid)
    p = f.people[r]
    return {
        "root": r, "home": _root(conn, f, pid),
        "pedigree": _node(f, r, 200 if depth == "full" else max(0, min(int(depth) if str(depth).isdigit() else 3, 30))),
        "generations": f.ancestors_depth(r),
        "spouses": [f.summary(s) for s in p.spouses],
        "children": [f.summary(c) for c in sorted(p.children, key=lambda c: (f.birth(c) or {}).get("lo") or 9999)],
        "siblings": [f.summary(s) for s in f.siblings(r)],
        "people": sorted(({"id": x.id, "name": x.name, "lifespan": f.summary(x.id)["lifespan"]} for x in f.people.values()),
                         key=lambda x: x["name"].lower()),
    }


@router.put("/projects/{pid}/tree/home")
def set_home(pid: str, body: dict = Body(...), conn=Depends(get_conn)):
    f = fam.load(conn, pid)
    if body.get("person_id") not in f.people:
        raise ValidationError("Choose a person in this project")
    roots = st.get(conn, "tree_roots") or {}
    roots[pid] = body["person_id"]
    st.put(conn, "tree_roots", roots)
    return {"ok": True}


def _timeline(f: fam.Family, pid: str) -> list:
    """One row per fact; duplicates (same type, year and place) are merged with their sources combined."""
    out: dict = {}
    for e in f.people[pid].events:
        if e.type in ("name",) or e.status == "rejected":
            continue
        key = (e.type, e.year, e.place.short() if e.place.raw else None, (e.value or "")[:40] if e.type in ("occupation", "other") else None)
        row = out.get(key)
        if not row:
            row = out[key] = {"type": e.type, "year": e.year, "date": e.date_text, "place": e.place.short() if e.place.raw else None,
                              "place_full": e.place.raw or None, "detail": e.place.detail, "value": e.value, "claim_ids": [], "sources": [],
                              "status": e.status}
        row["claim_ids"].append(e.claim_id)
        if e.date_text and (not row["date"] or len(e.date_text) > len(row["date"])):
            row["date"] = e.date_text
        for s in e.sources:
            if s["id"] not in (x["id"] for x in row["sources"]):
                row["sources"].append({"id": s["id"], "title": s["title"], "url": s["url"], "kind": s["kind"]})
    return sorted(out.values(), key=lambda r: (r["year"] if r["year"] is not None else 9999, ["birth", "baptism"].count(r["type"]) * -1))


@router.get("/persons/{person_id}/overview")
def overview(person_id: str, conn=Depends(get_conn)):
    r = conn.execute("SELECT project_id FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not r:
        raise NotFound("person")
    pid = r[0]
    f = fam.load(conn, pid)
    p = f.people[person_id]
    cl = checklist.build(f, person_id)
    leads = [h for h in eng.pending_review(conn, pid) if h["person_id"] == person_id][:50]
    runs = rows(conn, "SELECT id, mode, status, started_at, summary_json FROM research_runs WHERE person_id = ? ORDER BY started_at DESC LIMIT 5", (person_id,))
    return {
        **cl,
        "project_id": pid,
        "family": {
            "parents": [f.summary(x) for x in p.parents],
            "spouses": [f.summary(x) for x in p.spouses],
            "children": [f.summary(x) for x in sorted(p.children, key=lambda c: (f.birth(c) or {}).get("lo") or 9999)],
            "siblings": [f.summary(x) for x in f.siblings(person_id)],
        },
        "timeline": _timeline(f, person_id),
        "sources": sorted(p.sources.values(), key=lambda s: s["title"] or ""),
        "leads": leads,
        "runs": runs,
        "birth_basis": (f.birth(person_id) or {}).get("basis"),
    }


@router.get("/projects/{pid}/home")
def home(pid: str, conn=Depends(get_conn)):
    f = fam.load(conn, pid)
    r = _root(conn, f, pid)
    ops = checklist.opportunities(f, r, limit=24)
    waiting = len(eng.pending_review(conn, pid))
    runs = rows(conn, """SELECT r.id, r.mode, r.status, r.started_at, r.person_id, p.display_name AS person_name, r.summary_json FROM research_runs r
                         LEFT JOIN persons p ON p.id = r.person_id WHERE r.project_id = ? ORDER BY r.started_at DESC LIMIT 5""", (pid,))
    brick = [o for o in ops if o["item"]["group"] == "parents"]
    other = [o for o in ops if o["item"]["group"] != "parents"]
    return {"root": f.summary(r) if r else None, "people": len(f.people), "leads_waiting": waiting, "runs": runs,
            "brick_walls": brick[:8], "next_steps": other[:14]}


# ------------------------------------------------------------------ combining trees

@router.get("/projects/{pid}/combine/suggest")
def combine_suggest(pid: str, source: str, conn=Depends(get_conn)):
    return cmb.suggest(conn, pid, source)


@router.post("/projects/{pid}/combine")
def combine_run(pid: str, request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    if not body.get("source_project_id"):
        raise ValidationError("Choose the tree to bring in")
    return cmb.combine(conn, request.app.state.settings, pid, body["source_project_id"], body.get("pairs") or [])


@router.get("/projects/{pid}/combine/runs")
def combine_runs(pid: str, conn=Depends(get_conn)):
    return cmb.list_runs(conn, pid)


@router.post("/combine/{rid}/undo")
def combine_undo(rid: str, request: Request, conn=Depends(get_conn)):
    return cmb.undo(conn, request.app.state.settings, rid)
