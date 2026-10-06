"""AI service: configuration, model discovery, compatibility checks, runs, cancellation, proposals.

Guarantees:
* AI is off until the user enables it and acknowledges what will be sent.
* The provider/model used is exactly the one shown in the preview; nothing switches silently.
  Cross-provider fallback happens only if the user enabled it, and is recorded on the run.
* Duplicate submissions of an identical request while one is running are refused.
* Every run records provider, model id, timing, token usage (when reported), what was sent,
  and the source references of its output. Cost is "unknown" (no verified pricing source).
* Results become proposals; nothing changes research data until the user accepts a proposal.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

from .. import settings_store as st
from .. import workspace as ws
from ..db import connect, insert, new_id, now_iso, one, rows, today_iso, update
from ..directory import NotFound, ValidationError
from . import tasks as T
from .credentials import CredentialStore, mask
from .providers import PROVIDERS, AIError, GenerateRequest, elapsed_ms, make_adapter

COST_NOTE = "unknown — no verified pricing source is configured, so no cost estimate is shown"
FALLBACK_CODES = {"rate_limit", "provider_unavailable", "timeout", "network", "model_unavailable"}


class AIService:
    def __init__(self, settings, creds: CredentialStore, factories: dict | None = None):
        self.settings = settings
        self.creds = creds
        self.factories = factories or {}
        self._running: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------ config
    def _conn(self):
        return connect(self.settings.db_path)

    def get_config(self, conn) -> dict:
        cfg = st.get(conn, "ai")
        providers = {}
        for p, label in PROVIDERS.items():
            key = self.creds.get(p)
            cache = cfg["model_cache"].get(p) or {}
            providers[p] = {"label": label, "configured": bool(key), "key_hint": mask(key), "key_source": self.creds.source(p),
                            "keychain_available": self.creds.writable(),
                            "models_cached": len(cache.get("models") or []), "refreshed_at": cache.get("refreshed_at"),
                            "manual_models": cfg["manual_models"].get(p) or []}
        return {**cfg, "providers": providers, "tasks_available": {k: v["label"] for k, v in T.TASKS.items()}, "cost_note": COST_NOTE}

    def update_config(self, conn, patch: dict) -> dict:
        cfg = st.get(conn, "ai")
        allowed = {"enabled", "default", "tasks", "fallback", "timeout_seconds"}
        for k, v in patch.items():
            if k not in allowed:
                continue
            if k == "tasks":
                for task, o in (v or {}).items():
                    if task not in T.TASKS:
                        raise ValidationError(f"Unknown task {task}")
                    if o and o.get("provider") and o["provider"] not in PROVIDERS:
                        raise ValidationError("Unknown provider")
                cfg["tasks"] = {t: o for t, o in (v or {}).items() if o and (o.get("provider") or o.get("effort") or o.get("max_output_tokens"))}
            elif k in ("default", "fallback"):
                if v.get("provider") and v["provider"] not in PROVIDERS:
                    raise ValidationError("Unknown provider")
                cfg[k] = {**cfg[k], **v}
            elif k == "timeout_seconds":
                cfg[k] = max(10, min(600, int(v)))
            else:
                cfg[k] = bool(v)
        st.put(conn, "ai", cfg)
        return self.get_config(conn)

    def set_consent(self, conn, acknowledge: bool, allow_possibly_living: bool | None = None, allow_attachments: bool | None = None) -> dict:
        cfg = st.get(conn, "ai")
        c = cfg["consent"]
        c["acknowledged_at"] = now_iso() if acknowledge else None
        if allow_possibly_living is not None:
            c["allow_possibly_living"] = bool(allow_possibly_living)
        if allow_attachments is not None:
            c["allow_attachments"] = bool(allow_attachments)
        st.put(conn, "ai", cfg)
        return self.get_config(conn)

    def set_key(self, provider: str, key: str) -> None:
        if provider not in PROVIDERS:
            raise ValidationError("Unknown provider")
        key = (key or "").strip()
        if len(key) < 10 or any(ch.isspace() for ch in key):
            raise ValidationError("That does not look like an API key")
        try:
            self.creds.set(provider, key)
        except RuntimeError as e:
            raise ValidationError(str(e))

    def delete_key(self, provider: str) -> None:
        self.creds.delete(provider)

    def _adapter(self, conn, provider: str):
        key = self.creds.get(provider)
        if not key:
            raise AIError("no_key", f"No {PROVIDERS.get(provider, provider)} API key is configured. Add one in AI Settings.")
        timeout = st.get(conn, "ai")["timeout_seconds"]
        return make_adapter(provider, key, timeout, self.factories)

    # ------------------------------------------------------------ models
    async def refresh_models(self, provider: str) -> dict:
        conn = self._conn()
        try:
            adapter = self._adapter(conn, provider)
            models = await adapter.list_models()
            cfg = st.get(conn, "ai")
            cfg["model_cache"][provider] = {"models": models, "refreshed_at": now_iso()}
            st.put(conn, "ai", cfg)
            return {"provider": provider, "models": models, "refreshed_at": cfg["model_cache"][provider]["refreshed_at"], "cached": False}
        finally:
            conn.close()

    def cached_models(self, conn, provider: str) -> dict:
        cache = st.get(conn, "ai")["model_cache"].get(provider) or {}
        return {"provider": provider, "models": cache.get("models") or [], "refreshed_at": cache.get("refreshed_at"), "cached": True}

    async def validate_model(self, provider: str, model_id: str) -> dict:
        model_id = (model_id or "").strip()
        if not model_id or len(model_id) > 200 or any(ch.isspace() for ch in model_id):
            raise ValidationError("Enter a model id without spaces")
        conn = self._conn()
        try:
            adapter = self._adapter(conn, provider)
            entry = {"id": model_id, "validated_at": now_iso()}
            try:
                info = await adapter.retrieve_model(model_id)
                entry.update(ok=True, detail="Model found by the provider", info=info)
            except AIError as e:
                entry.update(ok=False, detail=e.message, code=e.code)
            cfg = st.get(conn, "ai")
            lst = [m for m in cfg["manual_models"].get(provider, []) if m["id"] != model_id] + [entry]
            cfg["manual_models"][provider] = lst
            st.put(conn, "ai", cfg)
            return entry
        finally:
            conn.close()

    def model_info(self, conn, provider: str, model_id: str) -> dict | None:
        cfg = st.get(conn, "ai")
        checked = next((x for x in cfg["manual_models"].get(provider) or [] if x["id"] == model_id), None)
        for m in (cfg["model_cache"].get(provider) or {}).get("models") or []:
            if m["id"] == model_id:
                src = "cached model list" + (f"; checked with the provider {checked['validated_at'][:16].replace('T', ' ')} UTC"
                                             + ("" if checked["ok"] else " — NOT available") if checked else " (not re-checked since)")
                return {**m, "info_source": src, "refreshed_at": cfg["model_cache"][provider].get("refreshed_at")}
        for m in cfg["manual_models"].get(provider) or []:
            if m["id"] == model_id and m.get("ok"):
                return {**(m.get("info") or {"id": model_id, "capabilities": {}}), "info_source": "manually validated", "refreshed_at": m["validated_at"]}
        return None

    # ------------------------------------------------------------ selection & compatibility
    def resolve(self, conn, task: str, override: dict | None) -> dict:
        cfg = st.get(conn, "ai")
        t = cfg["tasks"].get(task) or {}
        o = override or {}
        provider = o.get("provider") or t.get("provider") or cfg["default"].get("provider")
        model = o.get("model") or (t.get("model") if (t.get("provider") or provider) == provider else None) or (
            cfg["default"].get("model") if cfg["default"].get("provider") == provider else None)
        source = "per-run override" if o.get("model") else "task setting" if t.get("model") else "default"
        return {"provider": provider, "model": model, "source": source,
                "effort": o.get("effort", t.get("effort")),
                "max_output_tokens": int(o.get("max_output_tokens") or t.get("max_output_tokens") or T.TASKS[task]["default_max_output_tokens"])}

    def compatibility(self, conn, task: str, sel: dict, has_images=False, has_pdfs=False) -> dict:
        issues, unverified, controls = [], [], {"effort_levels": None, "max_output_tokens": None}
        if not sel.get("provider") or not sel.get("model"):
            return {"ok": False, "issues": ["Choose a provider and model for this task in AI Settings or below."], "unverified": [], "controls": controls}
        info = self.model_info(conn, sel["provider"], sel["model"])
        if info is None:
            return {"ok": False, "issues": [f"Model “{sel['model']}” is not in the cached list and has not been validated. "
                                            "Refresh the model list or validate the model id first."], "unverified": [], "controls": controls}
        caps = info.get("capabilities") or {}
        needs = T.TASKS[task]["needs"]

        def check(cap, label, needed):
            if not needed:
                return
            v = caps.get(cap)
            if v is False:
                issues.append(f"This model does not support {label}, which this task needs.")
            elif v is None:
                unverified.append(f"{label} support is not reported by the provider; it will be checked when the request runs.")
        check("structured_outputs", "structured (JSON) output", needs.get("structured_outputs"))
        check("image_input", "image input", has_images)
        if has_pdfs and sel["provider"] == "openai":
            issues.append("PDF input is only enabled for Anthropic models in this app; attach page images instead.")
        else:
            check("pdf_input", "PDF input", has_pdfs)
        if info.get("likely_text_model") is False:
            issues.append("The model id suggests this is not a text-generation model.")
        levels = caps.get("effort_levels")
        if sel["provider"] == "anthropic":
            controls["effort_levels"] = levels or []
            if sel.get("effort") and sel["effort"] not in (levels or []):
                issues.append(f"Effort “{sel['effort']}” is not supported by this model.")
        else:
            controls["effort_levels"] = None  # not reported by OpenAI; optional, validated at run time
            if sel.get("effort"):
                unverified.append("OpenAI does not report whether this model accepts reasoning effort; an unsupported value will be rejected.")
        mo = caps.get("max_output_tokens")
        controls["max_output_tokens"] = mo
        if mo and sel["max_output_tokens"] > mo:
            issues.append(f"Output limit {sel['max_output_tokens']} exceeds this model's maximum ({mo}).")
        return {"ok": not issues, "issues": issues, "unverified": unverified, "controls": controls,
                "info_source": info.get("info_source"), "refreshed_at": info.get("refreshed_at")}

    # ------------------------------------------------------------ preview & run
    def preview(self, conn, task: str, inputs: dict, override: dict | None = None) -> dict:
        if task not in T.TASKS:
            raise ValidationError("Unknown AI task")
        cfg = st.get(conn, "ai")
        sel = self.resolve(conn, task, override)
        try:
            payload = T.build_payload(conn, self.settings, task, inputs, cfg["consent"], None)
        except (ValueError, NotFound) as e:
            raise ValidationError(str(e))
        compat = self.compatibility(conn, task, sel, bool(payload.images), bool(payload.pdfs))
        blockers = list(payload.blocked)
        if not cfg["enabled"]:
            blockers.insert(0, "AI is disabled. Enable it in AI Settings.")
        if not cfg["consent"]["acknowledged_at"]:
            blockers.append("You have not yet opted in to sending research data to an external AI provider.")
        if sel.get("provider") and not self.creds.get(sel["provider"]):
            blockers.append(f"No {PROVIDERS[sel['provider']]} API key is configured.")
        fb = cfg["fallback"]
        return {"task": task, "task_label": T.TASKS[task]["label"], "selection": sel,
                "provider_label": PROVIDERS.get(sel.get("provider") or "", None),
                "compatibility": compat, "blockers": blockers, "can_run": not blockers and compat["ok"],
                "sent": {"items": payload.items, "total_chars": len(payload.text), "images": len(payload.images), "pdfs": len(payload.pdfs),
                         "destination": PROVIDERS.get(sel.get("provider") or "", "—"), "warnings": payload.warnings},
                "fallback": fb if fb.get("enabled") else None,
                "cost_note": COST_NOTE,
                "notice": "AI output is a research aid, not proof. Results appear as proposals for you to accept or reject."}

    def _request_key(self, task, inputs, sel) -> str:
        return hashlib.sha256(json.dumps([task, inputs, sel["provider"], sel["model"], sel.get("effort"), sel["max_output_tokens"]],
                                         sort_keys=True).encode()).hexdigest()[:24]

    async def start(self, conn, task: str, inputs: dict, override: dict | None, confirmed_model: str | None) -> dict:
        pv = self.preview(conn, task, inputs, override)
        if not pv["can_run"]:
            raise ValidationError(" ".join(pv["blockers"] + pv["compatibility"]["issues"]) or "Cannot run this task")
        sel = pv["selection"]
        if confirmed_model != f"{sel['provider']}:{sel['model']}":
            raise ValidationError("The selected model changed since the preview. Review the preview again before running.")
        key = self._request_key(task, inputs, sel)
        dup = one(conn, "SELECT id FROM ai_runs WHERE request_key = ? AND status = 'running'", (key,))
        if dup:
            raise DuplicateRun(dup["id"])
        project_id = self._project_of(conn, inputs)
        run_id = new_id()
        insert(conn, "ai_runs", {"id": run_id, "project_id": project_id, "task": task, "provider": sel["provider"], "model": sel["model"],
                                 "status": "running", "request_key": key, "sent_summary_json": json.dumps(pv["sent"]),
                                 "options_json": json.dumps({"effort": sel.get("effort"), "max_output_tokens": sel["max_output_tokens"],
                                                             "selection_source": sel["source"]}),
                                 "cost_note": COST_NOTE, "started_at": now_iso()})
        self._running[run_id] = asyncio.create_task(self._execute(run_id, task, inputs, sel, project_id))
        return self.get_run(conn, run_id)

    def _project_of(self, conn, inputs):
        if inputs.get("person_id"):
            return ws.get_person(conn, inputs["person_id"])["project_id"]
        if inputs.get("question_id"):
            return ws.get_question(conn, inputs["question_id"])["project_id"]
        if inputs.get("source_id"):
            s = one(conn, "SELECT project_id FROM sources WHERE id = ?", (inputs["source_id"],))
            return s and s["project_id"]
        return None

    async def _execute(self, run_id, task, inputs, sel, project_id):
        conn = self._conn()
        t0 = time.monotonic()
        try:
            cfg = st.get(conn, "ai")
            payload = T.build_payload(conn, self.settings, task, inputs, cfg["consent"], None)
            req = GenerateRequest(model=sel["model"], instructions=T.BASE_INSTRUCTIONS, text=T.user_prompt(task, payload),
                                  schema=T.TASKS[task]["schema"], schema_name=task, images=payload.images, pdfs=payload.pdfs,
                                  max_output_tokens=sel["max_output_tokens"], effort=sel.get("effort"))
            fallback_from = None
            try:
                result = await self._adapter(conn, sel["provider"]).generate(req)
            except AIError as e:
                fb = cfg["fallback"]
                if not (fb.get("enabled") and fb.get("provider") and fb.get("model") and e.code in FALLBACK_CODES
                        and (fb["provider"], fb["model"]) != (sel["provider"], sel["model"])):
                    raise
                fallback_from = f"{sel['provider']}:{sel['model']} ({e.code})"
                req.model, req.effort = fb["model"], None
                update(conn, "ai_runs", run_id, {"provider": fb["provider"], "model": fb["model"], "fallback_from": fallback_from})
                result = await self._adapter(conn, fb["provider"]).generate(req)
            src_text = "\n".join(l for l in payload.lines)
            props = T.proposals_from(task, result.parsed or {}, payload, src_text)
            ts = now_iso()
            for pr in props:
                insert(conn, "ai_proposals", {"id": new_id(), "run_id": run_id, "project_id": project_id, "kind": pr["kind"],
                                              "payload_json": json.dumps(pr["payload"], ensure_ascii=False), "basis": pr["basis"],
                                              "source_refs_json": json.dumps(pr["refs"], ensure_ascii=False), "created_at": ts})
            update(conn, "ai_runs", run_id, {"status": "succeeded", "output_text": result.text,
                                             "output_json": json.dumps(result.parsed, ensure_ascii=False) if result.parsed is not None else None,
                                             "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                                             "source_refs_json": json.dumps(list(payload.refmap.values()), ensure_ascii=False),
                                             "finished_at": now_iso(), "duration_ms": elapsed_ms(t0)})
        except asyncio.CancelledError:
            update(conn, "ai_runs", run_id, {"status": "cancelled", "error_code": "cancelled", "error_message": "Cancelled by user. Nothing was changed.",
                                             "finished_at": now_iso(), "duration_ms": elapsed_ms(t0)})
        except AIError as e:
            update(conn, "ai_runs", run_id, {"status": "failed", "error_code": e.code, "error_message": e.message,
                                             "finished_at": now_iso(), "duration_ms": elapsed_ms(t0)})
        except Exception as e:  # noqa: BLE001 — record, never crash the server
            update(conn, "ai_runs", run_id, {"status": "failed", "error_code": "internal", "error_message": f"Internal error: {type(e).__name__}",
                                             "finished_at": now_iso(), "duration_ms": elapsed_ms(t0)})
        finally:
            self._running.pop(run_id, None)
            conn.close()

    def cancel(self, conn, run_id: str) -> dict:
        task = self._running.get(run_id)
        run = self.get_run(conn, run_id)
        if run["status"] != "running":
            return run
        if task:
            task.cancel()
        else:  # orphaned (e.g. after a restart)
            update(conn, "ai_runs", run_id, {"status": "cancelled", "error_code": "cancelled", "error_message": "Cancelled", "finished_at": now_iso()})
        return self.get_run(conn, run_id)

    async def wait(self, run_id: str):
        t = self._running.get(run_id)
        if t:
            try:
                await t
            except asyncio.CancelledError:
                pass

    def get_run(self, conn, run_id: str) -> dict:
        r = one(conn, "SELECT * FROM ai_runs WHERE id = ?", (run_id,))
        if not r:
            raise NotFound("AI run")
        r["proposals"] = rows(conn, "SELECT * FROM ai_proposals WHERE run_id = ? ORDER BY created_at", (run_id,))
        return r

    def list_runs(self, conn, project_id: str | None = None) -> list[dict]:
        if project_id:
            return rows(conn, "SELECT * FROM ai_runs WHERE project_id = ? ORDER BY started_at DESC LIMIT 100", (project_id,))
        return rows(conn, "SELECT * FROM ai_runs ORDER BY started_at DESC LIMIT 100")

    def mark_orphans(self, conn) -> None:
        conn.execute("UPDATE ai_runs SET status = 'failed', error_code = 'interrupted', error_message = 'The app stopped while this run was in progress.' "
                     "WHERE status = 'running'")

    # ------------------------------------------------------------ live tests
    async def test_connection(self, provider: str) -> dict:
        t0 = time.monotonic()
        res = await self.refresh_models(provider)
        return {"ok": True, "detail": f"Connected. {len(res['models'])} models listed.", "duration_ms": elapsed_ms(t0),
                "charges": "Listing models does not generate text."}

    async def test_generation(self, provider: str, model: str) -> dict:
        conn = self._conn()
        try:
            t0 = time.monotonic()
            r = await self._adapter(conn, provider).generate(GenerateRequest(model=model, instructions="Reply with the single word OK.",
                                                                               text="Connection test.", max_output_tokens=16))
            return {"ok": True, "detail": f"Model replied: {r.text.strip()[:40]!r}", "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens, "duration_ms": elapsed_ms(t0), "charges": "This test may incur a small charge."}
        finally:
            conn.close()

    # ------------------------------------------------------------ proposals
    def decide(self, conn, proposal_id: str, accept: bool, edits: dict | None = None) -> dict:
        p = one(conn, "SELECT pr.*, r.provider, r.model, r.task FROM ai_proposals pr JOIN ai_runs r ON r.id = pr.run_id WHERE pr.id = ?", (proposal_id,))
        if not p:
            raise NotFound("proposal")
        if p["status"] != "pending":
            raise ValidationError("This proposal was already decided")
        created = None
        if accept:
            created = self._apply(conn, p, edits or {})
        update(conn, "ai_proposals", proposal_id, {"status": "accepted" if accept else "rejected", "decided_at": now_iso()})
        return {"status": "accepted" if accept else "rejected", "created": created}

    def _apply(self, conn, p: dict, edits: dict) -> dict | None:
        from .. import evidence as ev
        payload = {**p["payload"], **edits}
        tag = f"AI suggestion ({PROVIDERS.get(p['provider'])} {p['model']}), reviewed and accepted {today_iso()}"
        run = one(conn, "SELECT * FROM ai_runs WHERE id = ?", (p["run_id"],))
        refs = p.get("source_refs") or []
        person_ref = next((r for r in refs if r.get("type") == "person"), None)
        source_ref = next((r for r in refs if r.get("type") == "source"), None)
        inputs_person = None
        if not person_ref:
            for rr in (run.get("source_refs") or []):
                if rr.get("type") == "person":
                    inputs_person = rr
                    break
        person_id = (person_ref or inputs_person or {}).get("id")
        kind = p["kind"]
        if kind in ("research_step", "conflict_note", "observation", "note"):
            title = payload.get("title") or payload.get("text") or "AI suggestion"
            t = ws.create_task(conn, p["project_id"], {"title": ("Review: " if kind != "research_step" else "") + title[:300],
                                                        "notes": f"{payload.get('rationale') or ''}\n\n{tag}".strip(), "person_id": person_id,
                                                        "collection_id": payload.get("collection_id"), "origin": "ai_proposal"})
            return {"type": "task", "id": t["id"]}
        if kind == "query_variant":
            if not person_id:
                raise ValidationError("No person to attach this variant to")
            n = ws.add_name(conn, person_id, {"name_type": "variant", "full_text": payload["text"], "note": f"{payload.get('explanation', '')} — {tag}"})
            return {"type": "name", "id": n["id"]}
        if kind == "extracted_fact":
            if not edits.get("person_id"):
                raise ValidationError("Choose which person this fact is about before accepting it")
            src_id = (source_ref or {}).get("id")
            claim = ws.create_claim(conn, p["project_id"], {"person_id": edits["person_id"], "claim_type": edits.get("claim_type", "other"),
                                                            "date_text": edits.get("date_text"), "value_text": payload.get("value"),
                                                            "statement": f"{payload.get('field')}: {payload.get('value')}", "status": "tentative",
                                                            "status_note": tag})
            if src_id:
                ev.link_evidence(conn, claim["id"], src_id, {"stance": "supports", "identity_match": "uncertain", "assessment": "unassessed",
                                                             "interpretation_note": f"Quote: “{payload.get('quote', '')}” — basis: {p['basis']}. {tag}"})
            return {"type": "claim", "id": claim["id"]}
        if kind == "transcription":
            src_id = (source_ref or {}).get("id")
            if not src_id:
                raise ValidationError("No source to attach the transcription to")
            s = ev.get_source(conn, src_id)
            new = (s.get("transcription") or "") + f"\n\n--- {tag} ---\n{payload['text']}"
            ev.update_source(conn, src_id, {"transcription": new.strip()})
            return {"type": "source", "id": src_id}
        if kind == "summary":
            if not person_id:
                raise ValidationError("No person for this summary")
            per = ws.get_person(conn, person_id)
            ws.update_person(conn, person_id, {"notes": ((per.get("notes") or "") + f"\n\n--- {tag} ---\n{payload['text']}").strip()})
            return {"type": "person", "id": person_id}
        return None


class DuplicateRun(Exception):
    def __init__(self, run_id):
        super().__init__("duplicate")
        self.run_id = run_id
