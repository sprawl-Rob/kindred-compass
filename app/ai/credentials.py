"""API credential storage.

Keys are stored in the operating system's credential store via `keyring`
(macOS Keychain, Windows Credential Manager, Secret Service on Linux) — never in
the SQLite database, exports, backups, browser storage, or logs. If no keychain
is available, keys can be supplied through environment variables
(OPENAI_API_KEY / ANTHROPIC_API_KEY), which the app reads but never writes.
The browser only ever sees a masked hint such as "…3fQa".
"""
from __future__ import annotations

import os
from typing import Protocol

SERVICE = "kindred-compass"
ENV_VARS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


class CredentialStore(Protocol):
    def get(self, provider: str) -> str | None: ...
    def set(self, provider: str, secret: str) -> None: ...
    def delete(self, provider: str) -> None: ...
    def source(self, provider: str) -> str | None: ...
    def writable(self) -> bool: ...


class KeyringStore:
    def __init__(self):
        try:
            import keyring
            from keyring.backends import fail
            self._kr = keyring
            self._ok = not isinstance(keyring.get_keyring(), fail.Keyring)
        except Exception:  # pragma: no cover - environment specific
            self._kr, self._ok = None, False

    def writable(self) -> bool:
        return self._ok

    def _stored(self, provider: str) -> str | None:
        if not self._ok:
            return None
        try:
            return self._kr.get_password(SERVICE, provider)
        except Exception:
            return None

    def get(self, provider: str) -> str | None:
        return self._stored(provider) or os.environ.get(ENV_VARS.get(provider, "")) or None

    def source(self, provider: str) -> str | None:
        if self._stored(provider):
            return "system keychain"
        if os.environ.get(ENV_VARS.get(provider, "")):
            return f"environment variable {ENV_VARS[provider]}"
        return None

    def set(self, provider: str, secret: str) -> None:
        if not self._ok:
            raise RuntimeError("No system keychain is available. Set the "
                               f"{ENV_VARS.get(provider)} environment variable before starting the app instead.")
        self._kr.set_password(SERVICE, provider, secret)

    def delete(self, provider: str) -> None:
        if self._ok and self._stored(provider):
            self._kr.delete_password(SERVICE, provider)


class MemoryStore:
    """For tests."""

    def __init__(self, initial: dict | None = None):
        self._d = dict(initial or {})

    def writable(self) -> bool:
        return True

    def get(self, provider):
        return self._d.get(provider)

    def source(self, provider):
        return "memory" if provider in self._d else None

    def set(self, provider, secret):
        self._d[provider] = secret

    def delete(self, provider):
        self._d.pop(provider, None)


def mask(secret: str | None) -> str | None:
    if not secret:
        return None
    return "…" + secret[-4:] if len(secret) > 8 else "…"
