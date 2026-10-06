"""Key/value settings persisted in SQLite (never secrets)."""
from __future__ import annotations

import copy
import json

from .db import now_iso

DEFAULTS: dict = {
    "research_prefs": {"access": None, "subscriptions": [], "remote_only": False, "languages": []},
    "active_project": None,
    "ai": {
        "enabled": False,                       # "AI disabled" is the default
        "default": {"provider": None, "model": None},
        "tasks": {},                            # task -> {provider, model, effort, max_output_tokens}
        "consent": {"acknowledged_at": None, "allow_possibly_living": False, "allow_attachments": False},
        "fallback": {"enabled": False, "provider": None, "model": None},
        "timeout_seconds": 120,
        "model_cache": {},                      # provider -> {models: [...], refreshed_at}
        "manual_models": {},                    # provider -> [{id, validated_at, ok, detail}]
    },
}


def get(conn, key: str):
    r = conn.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
    default = copy.deepcopy(DEFAULTS.get(key))
    if not r:
        return default
    val = json.loads(r[0])
    if isinstance(default, dict) and isinstance(val, dict):
        return _merge(default, val)
    return val


def put(conn, key: str, value) -> None:
    conn.execute("INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
                 (key, json.dumps(value, ensure_ascii=False), now_iso()))


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out
