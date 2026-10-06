"""Automatic research runs: plan → search archives → check matches → save → log → hand off.

No AI is involved. For a person (and optional question) the engine:
1. plans queries from recorded names (and spelling variants), the research windows
   (years, places) and the archives that have implemented integrations and cover them;
2. runs each query against the archive's documented API, respecting its rate limit;
3. fetches item text where the archive allows it and checks whether the item really
   mentions this person (name, years, place), extracting the passage around the name;
4. stores every result with its reasons; strong matches are auto-saved as sources when
   that setting is on (marked "auto-saved, unreviewed"); others wait for review;
5. writes every search to the research log — including searches with no relevant results;
6. lists the best next manual searches for archives the app cannot search itself.
"""
from __future__ import annotations

import asyncio
import json

from .. import evidence as ev
from .. import recommend as rec
from .. import settings_store as st
from .. import workspace as ws
from ..db import connect, insert, new_id, now_iso, one, rows, today_iso, update
from ..directory import NotFound, ValidationError
from ..integrations import ADAPTERS, IntegrationError
from ..integrations.base import SearchQuery
from . import matching as mt

DEFAULTS = {"max_queries": 16, "results_per_query": 10, "fetch_text_top": 3, "auto_save": True, "adapters": None}
KEY_PREFIX = "archive:"


# ======================================================================= archives & keys

def archive_status(creds, conn=None) -> list[dict]:
    enabled = (st.get(conn, "archives") or {}) if conn is not None else {}
    out = []
    for key, cls in ADAPTERS.items():
        info = cls.describe()
        has_key = bool(creds.get(KEY_PREFIX + key)) if (cls.requires_key or cls.optional_key) else None
        info.update({"has_key": has_key, "enabled": enabled.get(key, True),
                     "usable": (not cls.requires_key or has_key) and enabled.get(key, True)})
        out.append(info)
    return out


def make_adapter(creds, key: str, blocking: bool = True, http_get=None):
    cls = ADAPTERS.get(key)
    if not cls:
        raise NotFound("archive integration")
    return cls(http_get=http_get, api_key=creds.get(KEY_PREFIX + key) if (cls.requires_key or cls.optional_key) else None, blocking=blocking)


# ======================================================================= planning

def _covers(cls, windows) -> tuple[bool, str]:
    cov = cls.coverage or {}
    if not windows:
        return True, "no place or dates recorded"
    countries = {c.lower() for c in cov.get("countries") or []}
    yf, yt = cov.get("from"), cov.get("to")
    ok_any = False
    for w in windows:
        c = (w.place.country or "").lower()
        if countries and c and not (c in countries or (c in ("usa", "united states", "us") and "united states" in countries)):
            continue
        if yf and w.year_to is not None and w.year_to < yf:
            continue
        if yt and w.year_from is not None and w.year_from > yt:
            continue
        ok_any = True
    return ok_any, ("covers the person's places and years" if ok_any else "outside this archive's coverage")


def plan(conn, creds, project_id: str, person_id: str, question_id: str | None, options: dict) -> dict:
    person = ws.get_person(conn, person_id)
    if person["project_id"] != project_id:
        raise ValidationError("Person belongs to a different project")
    question = ws.get_question(conn, question_id) if question_id else None
    windows = rec.research_windows(person, question)
    yfs = [w.year_from for w in windows if w.year_from is not None]
    yts = [w.year_to for w in windows if w.year_to is not None]
    yf, yt = (min(yfs) if yfs else None), (max(yts) if yts else None)
    states = []
    for w in windows:
        if (w.place.country or "").lower() in ("united states", "usa", "us") and w.place.region and w.place.region not in states:
            states.append(w.place.region)
    specs = name_queries(conn, project_id, person_id, person, (yf, yt), states)
    from .. import family as fam
    fam_ = fam.load(conn, project_id)
    statuses = {a["key"]: a for a in archive_status(creds, conn)}
    chosen = options.get("adapters") or list(statuses)   # unusable ones are reported as skipped, with the reason
    queries, skipped = [], []
    for key in chosen:
        a = statuses.get(key)
        if not a:
            continue
        if not a["usable"]:
            skipped.append({"adapter": key, "label": a["label"], "reason": "needs your API key" if a["requires_key"] and not a["has_key"] else "turned off"})
            continue
        cls = ADAPTERS[key]
        if getattr(cls, "plan_for", None):
            if fam_ is None or person_id not in fam_.people:
                skipped.append({"adapter": key, "label": a["label"], "reason": "person not found in the family graph"})
                continue
            cqs, why_not = cls.plan_for(fam_, person_id)
            if not cqs:
                skipped.append({"adapter": key, "label": a["label"], "reason": why_not})
                continue
            for cq in cqs:
                queries.append({"adapter": key, "label": a["label"], "query": {"text": cq["text"], "phrase": False, "year_from": cq["years"][0],
                                                                             "year_to": cq["years"][1], "state": cq.get("state"), "place": cq.get("place")},
                                "reason": cq["why"]})
            continue
        ok, why = _covers(cls, windows)
        if not ok:
            skipped.append({"adapter": key, "label": a["label"], "reason": why})
            continue
        cov = cls.coverage or {}
        qf = max(yf, cov["from"]) if (yf and cov.get("from")) else yf
        qt = min(yt, cov["to"]) if (yt and cov.get("to")) else yt
        for spec in specs:
            if spec.get("newspapers_only") and "newspaper" not in (cls.record_kind or ""):
                continue
            sf, st_ = spec.get("years") or (yf, yt)
            qf2 = max(sf, cov["from"]) if (sf and cov.get("from")) else sf
            qt2 = min(st_, cov["to"]) if (st_ and cov.get("to")) else st_
            if qf2 and qt2 and qf2 > qt2:
                continue
            for stt in (spec.get("states") or states[:2] or [None]):
                queries.append({"adapter": key, "label": a["label"], "query": {"text": spec["text"], "phrase": True, "year_from": qf2, "year_to": qt2,
                                                                             "state": stt if "United States" in (cov.get("countries") or []) else None},
                                "reason": f"{spec['why']}; {why}" + (f"; limited to {stt}" if stt else "")})
    # Interleave archives so a small budget still reaches each of them.
    by_adapter: dict = {}
    for q in queries:
        by_adapter.setdefault(q["adapter"], []).append(q)
    ordered = []
    while any(by_adapter.values()):
        for k in list(by_adapter):
            if by_adapter[k]:
                ordered.append(by_adapter[k].pop(0))
    limit = int(options.get("max_queries") or DEFAULTS["max_queries"])
    return {"person": {"id": person["id"], "name": person["display_name"]}, "queries": ordered[:limit], "dropped": max(0, len(ordered) - limit),
            "skipped_archives": skipped, "years": [yf, yt], "names": list(dict.fromkeys(x["text"] for x in specs)),
            "windows": [{"place": w.place_label or w.place.label(), "years": f"{w.year_from}–{w.year_to}", "basis": w.basis} for w in windows]}


def profile_for(conn, project_id: str, person: dict, windows) -> "mt.Profile":
    from .. import family as fam
    f = fam.load(conn, project_id)
    w = [{"year_from": x.year_from, "year_to": x.year_to} for x in windows]
    if person["id"] in f.people:
        return mt.Profile.from_family(f, person["id"], w)
    relatives = [c["related_person_name"] for c in person["claims"] if c.get("related_person_name")]
    return mt.Profile.from_person(person, w, relatives)


def name_queries(conn, project_id: str, person_id: str, person: dict, years: tuple, states: list) -> list:
    """The searches worth running for this person, most useful first: the recorded name, a targeted death-notice search,
    married and "Mrs." forms for women, the nicknames / anglicized forms records used, and surname spellings."""
    from .. import family as fam, nameequiv
    f = fam.load(conn, project_id)
    fp = f.people.get(person_id)
    out: list = []

    def add(text, why, years=None, states_=None):
        text = " ".join(text.split())
        if len(text.split()) < 2 or any(o["text"].lower() == text.lower() and o.get("years") == years for o in out):
            return
        out.append({"text": text, "why": why, "years": years, "states": states_})
    if not fp:
        add(person["display_name"], "display name")
        return out
    given = (fp.givens[0].split()[0] if fp.givens else "")
    surname = fp.surnames[0] if fp.surnames else (fp.married_surnames[0] if fp.married_surnames else "")
    if given and surname:
        add(f"{given} {surname}", "recorded name")
    elif fp.name:
        add(fp.name, "display name")
    d = f.death(person_id)
    if d and given and surname and d["hi"] <= 1963:
        dp = next((e.place for e in fp.ev("death", "burial") if e.place.state), None)
        add(f"{given} {surname}", "death notice or obituary (searching the year of death)", (d["lo"], d["hi"] + 1),
            [dp.state] if dp and dp.is_us else None)
        out[-1]["newspapers_only"] = True
    female = (fp.sex or "").upper().startswith("F")
    if female and given:
        for sp in fp.spouses[:2]:
            spp = f.people[sp]
            ms = spp.surnames[0] if spp.surnames else None
            if ms and ms.lower() != surname.lower():
                add(f"{given} {ms}", f"married name (wife of {spp.name})")
            if ms and spp.givens:
                add(f"Mrs. {spp.givens[0].split()[0]} {ms}", "newspapers usually named married women by their husband's name")
        for ms in fp.married_surnames[:1]:
            add(f"{given} {ms}", "recorded married name")
    if given and surname:
        nick = nameequiv.nickname_in_quotes(fp.givens[0])
        if nick:
            add(f"{nick} {surname}", f"the name {given} went by (“{nick}” in your tree)")
        plain = nameequiv.strip_quoted(fp.givens[0]).split()
        if len(plain) > 1 and len(plain[1].strip(".")) > 2:
            add(f"{plain[1]} {surname}", "middle name — people often went by it")
        eq = [e for e in nameequiv.given_equivalents(given) if len(e) > 2 and not nameequiv.is_abbreviation(e)]
        for e in eq[:2]:
            add(f"{e} {surname}", f"“{e}” was commonly written for {given}")
        from .. import names as nm
        sv = list(dict.fromkeys(nameequiv.surname_variants(surname) + nm.spelling_variants(surname)))
        for v in sv[:2]:
            add(f"{given} {v}", f"spelling variant of the surname (“{v}”)")
    return out


# ======================================================================= running

class ResearchService:
    def __init__(self, settings, creds, http_get=None):
        self.settings = settings
        self.creds = creds
        self.http_get = http_get           # tests inject a fake HTTP layer
        self._tasks: dict = {}
        self._cancel: set = set()

    def _conn(self):
        return connect(self.settings.db_path)

    async def start(self, conn, project_id: str, person_id: str, question_id: str | None, options: dict) -> dict:
        opts = {**DEFAULTS, **{k: v for k, v in (options or {}).items() if k in DEFAULTS}}
        if one(conn, "SELECT id FROM research_runs WHERE person_id = ? AND status = 'running' AND mode = 'automatic'", (person_id,)):
            raise ValidationError("A research run for this person is already in progress.")
        pl = plan(conn, self.creds, project_id, person_id, question_id, opts)
        if not pl["queries"]:
            raise ValidationError("No archive the app can search covers this person's places and years"
                                  + (" (" + "; ".join(f"{s['label']}: {s['reason']}" for s in pl["skipped_archives"]) + ")" if pl["skipped_archives"] else "")
                                  + ". See Next searches for manual searches.")
        rid = new_id()
        insert(conn, "research_runs", {"id": rid, "project_id": project_id, "person_id": person_id, "question_id": question_id, "mode": "automatic",
                                       "status": "running", "options_json": json.dumps(opts), "plan_json": json.dumps(pl, default=str),
                                       "progress_json": json.dumps({"done": 0, "total": len(pl["queries"]), "current": None}),
                                       "started_at": now_iso()})
        self._tasks[rid] = asyncio.create_task(self._execute(rid))
        return self.get(conn, rid)

    def cancel(self, conn, run_id: str) -> dict:
        self._cancel.add(run_id)
        t = self._tasks.get(run_id)
        run = self.get(conn, run_id)
        if run["status"] == "running" and not t:
            update(conn, "research_runs", run_id, {"status": "cancelled", "finished_at": now_iso()})
        return self.get(conn, run_id)

    async def wait(self, run_id: str):
        t = self._tasks.get(run_id)
        if t:
            try:
                await t
            except asyncio.CancelledError:
                pass

    async def _execute(self, run_id: str):
        conn = self._conn()
        try:
            run = one(conn, "SELECT * FROM research_runs WHERE id = ?", (run_id,))
            opts, pl = run["options"], run["plan"]
            person = ws.get_person(conn, run["person_id"])
            question = ws.get_question(conn, run["question_id"]) if run["question_id"] else None
            windows = rec.research_windows(person, question)
            prof = profile_for(conn, run["project_id"], person, windows)
            known = {r["dedupe_key"]: r for r in rows(conn, "SELECT dedupe_key, status FROM research_hits WHERE person_id = ? AND status != 'candidate'",
                                                        (person["id"],))}
            seen: dict = {}
            stats = {"queries_run": 0, "results_returned": 0, "checked": 0, "strong": 0, "possible": 0, "weak": 0, "auto_saved": 0,
                     "already_reviewed": 0, "errors": 0}
            errors = []
            for i, q in enumerate(pl["queries"]):
                if run_id in self._cancel:
                    raise asyncio.CancelledError()
                update(conn, "research_runs", run_id, {"progress_json": json.dumps({"done": i, "total": len(pl["queries"]),
                                                                                    "current": f"{q['label']}: {q['query']['text']}"})})
                adapter = make_adapter(self.creds, q["adapter"], blocking=True, http_get=self.http_get)
                sq = SearchQuery(**{k: v for k, v in q["query"].items() if k in SearchQuery.__dataclass_fields__},
                                 page_size=int(opts["results_per_query"]))
                try:
                    res = await asyncio.to_thread(adapter.search, sq)
                except IntegrationError as e:
                    stats["errors"] += 1
                    errors.append(f"{q['label']} — {q['query']['text']}: {e.message}")
                    self._log(conn, run, q, sq, None, [], e.message)
                    continue
                stats["queries_run"] += 1
                stats["results_returned"] += len(res.hits)
                found = []
                for j, h in enumerate(res.hits):
                    if run_id in self._cancel:
                        raise asyncio.CancelledError()
                    key = mt.dedupe_key(q["adapter"], h.item_id, h.url)
                    if key in seen:
                        if seen[key]:
                            found.append(seen[key])   # same item found again by this query
                        continue
                    seen[key] = None
                    if key in known:
                        stats["already_reviewed"] += 1
                        continue
                    text = None
                    if adapter.supports_text and j < int(opts["fetch_text_top"]):
                        try:
                            text = await asyncio.to_thread(adapter.fetch_text, h)
                        except IntegrationError:
                            text = None
                    m = mt.evaluate(prof, h.title, h.snippet, text, h.date_text, (h.extra or {}).get("match_place", h.place_text))
                    stats["checked"] += 1
                    stats[m.strength] += 1
                    hid = new_id()
                    insert(conn, "research_hits", {"id": hid, "run_id": run_id, "project_id": run["project_id"], "person_id": person["id"],
                                                   "adapter": q["adapter"], "found_by": "search", "query_text": sq.text, "item_id": h.item_id,
                                                   "title": (h.title or "")[:500], "date_text": h.date_text, "url": h.url, "snippet": h.snippet,
                                                   "context": m.context, "place_text": h.place_text, "collection": h.collection,
                                                   "record_kind": h.record_kind, "score": m.score, "strength": m.strength,
                                                   "reasons_json": json.dumps(m.reasons + ([] if text else ["Full text not checked — only the title and snippet"] if adapter.supports_text else [])),
                                                   "status": "candidate", "dedupe_key": key, "created_at": now_iso()})
                    if m.strength in (mt.STRONG, mt.POSSIBLE):
                        found.append((hid, m))
                        seen[key] = (hid, m)
                    if m.strength == mt.STRONG and opts.get("auto_save"):
                        save_hit(conn, hid, auto=True)
                        stats["auto_saved"] += 1
                self._log(conn, run, q, sq, res, found, None)
            summary = {"stats": stats, "errors": errors, "manual_next": manual_next(conn, run["project_id"], person["id"], run["question_id"]),
                       "note": "Scores order results; they are not the probability that a record is about this person."}
            update(conn, "research_runs", run_id, {"status": "completed", "summary_json": json.dumps(summary, default=str), "finished_at": now_iso(),
                                                   "progress_json": json.dumps({"done": len(pl["queries"]), "total": len(pl["queries"]), "current": None})})
        except asyncio.CancelledError:
            update(conn, "research_runs", run_id, {"status": "cancelled", "finished_at": now_iso()})
        except Exception as e:  # noqa: BLE001
            update(conn, "research_runs", run_id, {"status": "failed", "error": f"{type(e).__name__}: {e}"[:500], "finished_at": now_iso()})
        finally:
            self._tasks.pop(run_id, None)
            self._cancel.discard(run_id)
            conn.close()

    def _log(self, conn, run, q, sq, res, found, error):
        col = one(conn, "SELECT id FROM collections WHERE seed_key = ?", (ADAPTERS[q["adapter"]].collection_seed_keys[0],)) \
            if ADAPTERS[q["adapter"]].collection_seed_keys else None
        if error:
            outcome, note = "inaccessible", f"Automatic search could not run: {error}"
        elif found:
            outcome = "possible_match"
            note = f"Automatic search: {len(res.hits)} result(s) returned; {len(found)} look like this person — review them in the research run."
        else:
            outcome = "no_result"
            note = (f"Automatic search: {len(res.hits)} result(s) returned (of {res.total if res.total is not None else 'unknown'} total); "
                    "none clearly mention this person among the results checked. That does not mean no record exists.")
        filters = ", ".join(x for x in [f"years {sq.year_from}–{sq.year_to}" if sq.year_from or sq.year_to else "", f"state {sq.state}" if sq.state else "",
                                         "exact phrase" if sq.phrase else ""] if x)
        insert(conn, "research_log", {"id": new_id(), "project_id": run["project_id"], "person_id": run["person_id"], "question_id": run["question_id"],
                                      "collection_id": col and col["id"], "resource_text": None if col else q["label"],
                                      "query_text": sq.text, "name_variants_json": json.dumps([sq.text]), "filters_text": filters or None,
                                      "year_from": sq.year_from, "year_to": sq.year_to, "place_text": sq.state, "searched_on": today_iso(),
                                      "outcome": outcome, "result_url": res.query_url if res else None, "notes": note, "origin": "automatic",
                                      "run_id": run["id"], "created_at": now_iso(), "updated_at": now_iso()})

    def get(self, conn, run_id: str) -> dict:
        r = one(conn, "SELECT * FROM research_runs WHERE id = ?", (run_id,))
        if not r:
            raise NotFound("research run")
        r["hits"] = rows(conn, "SELECT * FROM research_hits WHERE run_id = ? ORDER BY CASE status WHEN 'rejected' THEN 1 ELSE 0 END, score DESC", (run_id,))
        return r

    def list(self, conn, project_id: str, person_id: str | None = None) -> list[dict]:
        sql = "SELECT id, person_id, question_id, mode, status, started_at, finished_at, summary_json, progress_json, ai_model FROM research_runs WHERE project_id = ?"
        params = [project_id]
        if person_id:
            sql += " AND person_id = ?"
            params.append(person_id)
        return rows(conn, sql + " ORDER BY started_at DESC LIMIT 50", params)

    def mark_orphans(self, conn):
        conn.execute("UPDATE research_runs SET status = 'interrupted', finished_at = ? WHERE status = 'running'", (now_iso(),))
        trim_expired(conn)


MATCHER_VERSION = 2


def rescore_pending(conn) -> int:
    """Re-check unreviewed results with the current matcher (once per matcher version).
    Only the stored title, snippet and passage are available, so the check uses those."""
    from .. import family as fam, settings_store as st
    if (st.get(conn, "matcher_version") or 1) >= MATCHER_VERSION:
        return 0
    n = 0
    fams: dict = {}
    for h in rows(conn, "SELECT * FROM research_hits WHERE status IN ('candidate', 'auto_saved', 'maybe')"):
        if not h["person_id"]:
            continue
        f = fams.get(h["project_id"]) or fams.setdefault(h["project_id"], fam.load(conn, h["project_id"]))
        if h["person_id"] not in f.people:
            continue
        prof = mt.Profile.from_family(f, h["person_id"])
        m = mt.evaluate(prof, h["title"], h["snippet"], h["context"], h["date_text"], h["place_text"])
        update(conn, "research_hits", h["id"], {"score": m.score, "strength": m.strength,
                                                "reasons_json": json.dumps(m.reasons + ["Re-checked with the stricter match rules (October 2026)"])})
        n += 1
    st.put(conn, "matcher_version", MATCHER_VERSION)
    return n


def trim_expired(conn) -> int:
    """Some providers limit how long their metadata may be kept. Saved sources are your research notes and are kept;
    unsaved results from those providers have their text removed once the limit passes."""
    from datetime import datetime, timedelta, timezone
    n = 0
    for key, cls in ADAPTERS.items():
        if cls.cache_days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=cls.cache_days)).isoformat()
            cur = conn.execute("""UPDATE research_hits SET snippet = NULL, context = NULL, reasons_json = ?
                                  WHERE adapter = ? AND status IN ('candidate', 'maybe', 'rejected') AND created_at < ? AND snippet IS NOT NULL""",
                               (json.dumps(["Text removed after the provider's caching limit"]), key, cutoff))
            n += cur.rowcount
    return n


# ======================================================================= saving & review

def _found_claim(conn, project_id: str, person_id: str) -> str:
    """A per-person holder claim for records found by searching, until the user links them to specific facts."""
    c = one(conn, "SELECT id FROM claims WHERE person_id = ? AND claim_type = 'other' AND value_text = 'Records found by research runs'", (person_id,))
    if c:
        return c["id"]
    return ws.create_claim(conn, project_id, {"person_id": person_id, "claim_type": "other", "value_text": "Records found by research runs",
                                              "statement": "Holds records found by automatic or AI-assisted searches. Link each one to the specific fact it "
                                                           "supports once you have reviewed it.", "status": "working"})["id"]


def save_hit(conn, hit_id: str, auto: bool = False, claim_id: str | None = None, stance: str = "mentions",
             identity: str | None = None) -> dict:
    h = one(conn, "SELECT * FROM research_hits WHERE id = ?", (hit_id,))
    if not h:
        raise NotFound("result")
    sid = h["source_id"]
    if not sid or not one(conn, "SELECT id FROM sources WHERE id = ?", (sid,)):
        label = {"automatic": "automatic archive search", "ai": "AI research assistant", "web": "AI web search"}.get(
            {"search": "automatic", "ai": "ai", "web": "web"}[h["found_by"]], "search")
        title = h["title"] or h["url"] or "Found record"
        vals = {"title": title[:500], "repository": None, "collection_name": h["collection"], "record_date_text": h["date_text"], "url": h["url"],
                "accessed_on": today_iso(), "excerpt": h["context"] or h["snippet"] or h["quote"],
                "record_format": "newspaper" if (h["record_kind"] or "").startswith("newspaper") else "unknown",
                "provenance_note": (f"{'Auto-saved' if auto else 'Saved'} from {label} on {today_iso()} (query “{h['query_text']}”). "
                                    + ("UNREVIEWED — saved automatically because it looked like a strong match. " if auto else "")
                                    + "Why it matched: " + "; ".join(h["reasons"] or [])),
                "allow_duplicate": True}
        s = ev.create_source(conn, h["project_id"], vals)
        sid = s["id"]
        conn.execute("UPDATE sources SET origin = ? WHERE id = ?", ("auto" if auto else "research", sid))
    target = claim_id or _found_claim(conn, h["project_id"], h["person_id"])
    ev.link_evidence(conn, target, sid, {"stance": stance, "identity_match": identity or ("possible" if auto else "probable"),
                                         "assessment": "unassessed",
                                         "interpretation_note": ("Auto-saved strong match — not yet reviewed. " if auto else "") + (h["context"] or "")[:500]})
    update(conn, "research_hits", hit_id, {"status": "auto_saved" if auto else "saved", "source_id": sid, "decided_at": None if auto else now_iso()})
    return one(conn, "SELECT * FROM research_hits WHERE id = ?", (hit_id,))


def decide_hit(conn, hit_id: str, action: str, claim_id: str | None = None, stance: str | None = None, identity: str | None = None) -> dict:
    out = _decide_one(conn, hit_id, action, claim_id, stance, identity)
    # The same item found again by other searches or runs gets the same answer.
    h = one(conn, "SELECT * FROM research_hits WHERE id = ?", (hit_id,))
    for d in rows(conn, """SELECT * FROM research_hits WHERE person_id = ? AND dedupe_key = ? AND id != ?
                           AND status IN ('candidate', 'maybe', 'auto_saved')""", (h["person_id"], h["dedupe_key"], hit_id)):
        if d["source_id"] and d["status"] == "auto_saved" and d["source_id"] != h["source_id"]:
            src = one(conn, "SELECT origin FROM sources WHERE id = ?", (d["source_id"],))
            if src and src["origin"] in ("auto", "research"):
                conn.execute("DELETE FROM sources WHERE id = ?", (d["source_id"],))
        update(conn, "research_hits", d["id"], {"status": h["status"], "source_id": h["source_id"], "decided_at": now_iso()})
    return out


def _decide_one(conn, hit_id: str, action: str, claim_id: str | None = None, stance: str | None = None, identity: str | None = None) -> dict:
    h = one(conn, "SELECT * FROM research_hits WHERE id = ?", (hit_id,))
    if not h:
        raise NotFound("result")
    if action == "save":
        if claim_id:
            c = ws.get_claim(conn, claim_id)
            if c["person_id"] != h["person_id"]:
                raise ValidationError("That claim belongs to a different person")
        out = save_hit(conn, hit_id, auto=False, claim_id=claim_id, stance=stance or ("supports" if claim_id else "mentions"), identity=identity)
        if h["status"] == "auto_saved":
            # Confirming an auto-saved match: it is now reviewed.
            if h["source_id"]:
                note = one(conn, "SELECT provenance_note FROM sources WHERE id = ?", (h["source_id"],))["provenance_note"] or ""
                update(conn, "sources", h["source_id"], {"provenance_note": note.replace("UNREVIEWED — saved automatically because it looked like a strong match. ",
                                                                                         f"Reviewed and kept on {today_iso()}. "), "updated_at": now_iso()})
        return out
    if action == "maybe":
        update(conn, "research_hits", hit_id, {"status": "maybe", "decided_at": now_iso()})
    elif action == "reject":
        if h["source_id"] and h["status"] in ("auto_saved", "saved"):
            src = one(conn, "SELECT * FROM sources WHERE id = ?", (h["source_id"],))
            if src and src["origin"] in ("auto", "research"):
                conn.execute("DELETE FROM sources WHERE id = ?", (src["id"],))   # remove the record that was saved from this result
        update(conn, "research_hits", hit_id, {"status": "rejected", "source_id": None, "decided_at": now_iso()})
    else:
        raise ValidationError("Unknown action")
    return one(conn, "SELECT * FROM research_hits WHERE id = ?", (hit_id,))


def manual_next(conn, project_id: str, person_id: str, question_id: str | None, limit: int = 6) -> list[dict]:
    """The best searches the app cannot run itself — handed off with links and queries."""
    r = rec.recommend(conn, project_id, person_id=person_id, question_id=question_id, limit=30)
    out = []
    for x in r["recommendations"]:
        if x["collection"].get("adapter_key"):
            continue
        out.append({"collection_id": x["collection"]["id"], "name": x["collection"]["name"], "provider": x["collection"]["provider_name"],
                    "headline": x["headline"], "next_action": x["next_action"], "query": x["suggested_query"]["text"],
                    "variants": x["suggested_query"]["variants"][:5]})
        if len(out) >= limit:
            break
    return out


def pending_review(conn, project_id: str) -> list[dict]:
    return rows(conn, """SELECT h.*, p.display_name AS person_name FROM research_hits h LEFT JOIN persons p ON p.id = h.person_id
                         WHERE h.id IN (SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY person_id, dedupe_key ORDER BY score DESC, created_at) AS rn
                                                        FROM research_hits WHERE project_id = ? AND status IN ('candidate', 'auto_saved', 'maybe')
                                                        AND strength != 'weak') WHERE rn = 1)
                         ORDER BY h.score DESC LIMIT 200""", (project_id,))

