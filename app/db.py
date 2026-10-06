"""SQLite access and schema migrations.

Migrations are plain SQL files in app/migrations named NNN_description.sql and
are applied in order; the applied version is tracked in PRAGMA user_version.
A backup copy of the database is taken automatically before any migration runs
on an existing, non-empty database.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def now_iso() -> str:
    # Microsecond precision: import/undo logic compares timestamps to detect later imports and local edits.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def today_iso() -> str:
    return date.today().isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def connect(db_path: Path) -> sqlite3.Connection:
    # One connection per request; FastAPI may open and close it on different worker threads,
    # but it is never used concurrently, so the same-thread check is disabled.
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None, check_same_thread=False)  # autocommit; explicit transactions
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


class Tx:
    """`with Tx(conn):` runs a block in a transaction (BEGIN IMMEDIATE / COMMIT / ROLLBACK)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.nested = conn.in_transaction

    def __enter__(self):
        if not self.nested:
            self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if self.nested:
            return False
        if exc_type is None:
            self.conn.execute("COMMIT")
        else:
            self.conn.execute("ROLLBACK")
        return False


def migration_files() -> list[tuple[int, Path]]:
    out = []
    for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = re.match(r"(\d+)_", p.name)
        if m:
            out.append((int(m.group(1)), p))
    return out


def latest_version() -> int:
    files = migration_files()
    return files[-1][0] if files else 0


def migrate(conn: sqlite3.Connection, db_path: Path | None = None) -> int:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    pending = [(v, p) for v, p in migration_files() if v > current]
    if not pending:
        return current
    if current > 0 and db_path is not None and db_path.exists():
        bak = db_path.with_name(f"{db_path.stem}.pre-migration-v{current}.sqlite3")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(db_path, bak)
    for version, path in pending:
        sql = path.read_text(encoding="utf-8")
        conn.executescript("BEGIN;\n" + sql + f"\nPRAGMA user_version = {version};\nCOMMIT;")
    return conn.execute("PRAGMA user_version").fetchone()[0]


# ---------------------------------------------------------------- helpers

JSON_SUFFIX = "_json"


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert a row; decode *_json columns into `name` without the suffix."""
    if row is None:
        return None
    out: dict[str, Any] = {}
    for k in row.keys():
        v = row[k]
        if k.endswith(JSON_SUFFIX):
            out[k[: -len(JSON_SUFFIX)]] = json.loads(v) if v else None
        else:
            out[k] = v
    return out


def rows(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> list[dict]:
    return [row_to_dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def one(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> dict | None:
    return row_to_dict(conn.execute(sql, tuple(params)).fetchone())


def to_columns(data: dict, json_fields: Iterable[str]) -> dict:
    """Encode python values into DB columns: json fields get the _json suffix."""
    jf = set(json_fields)
    out = {}
    for k, v in data.items():
        if k in jf:
            out[k + JSON_SUFFIX] = json.dumps(v if v is not None else [], ensure_ascii=False)
        elif isinstance(v, bool):
            out[k] = int(v)
        else:
            out[k] = v
    return out


_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _check_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"bad identifier {name!r}")
    return name


def insert(conn: sqlite3.Connection, table: str, values: dict) -> None:
    cols = [_check_ident(c) for c in values]
    conn.execute(
        f"INSERT INTO {_check_ident(table)} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
        tuple(values.values()),
    )


def update(conn: sqlite3.Connection, table: str, row_id: str, values: dict) -> None:
    if not values:
        return
    sets = ", ".join(f"{_check_ident(c)} = ?" for c in values)
    conn.execute(f"UPDATE {_check_ident(table)} SET {sets} WHERE id = ?", (*values.values(), row_id))
