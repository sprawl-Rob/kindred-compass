"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Request

from .db import connect


def get_conn(request: Request):
    conn = connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()
