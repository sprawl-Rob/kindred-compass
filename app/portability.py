"""Export, import, CSV, backup and restore.

* Full JSON export/import: every table (directory, research data, settings). API
  credentials are never in the database, so they are never exported.
* Project export/import: one project's research data (+ optional attachments,
  base64-encoded). Import always creates a new project with fresh ids, so it can
  never overwrite existing work.
* Backup (.zip): a consistent SQLite snapshot + the attachments folder + a manifest
  with SHA-256 checksums. Restore validates the archive, takes a safety backup of
  the current data first, then replaces it.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from . import config
from .db import Tx, connect, latest_version, migrate, new_id, now_iso
from .directory import ValidationError

EXPORT_FORMAT = "kindred-compass-export"
PROJECT_FORMAT = "kindred-compass-project"
BACKUP_FORMAT = "kindred-compass-backup"
FORMAT_VERSION = 1

# Order matters for inserts (foreign keys).
ALL_TABLES = ["providers", "collections", "collection_relations", "directory_history", "seed_state", "pathways",
              "projects", "places", "persons", "person_names", "claims", "research_questions", "tasks", "bookmarks",
              "research_log", "sources", "claim_evidence", "attachments", "settings", "ai_runs", "ai_proposals",
              "import_lineages", "import_batches", "import_records", "import_links", "import_changes", "import_media", "import_review_items"]
PROJECT_TABLES = ["places", "persons", "person_names", "claims", "research_questions", "tasks", "bookmarks",
                  "research_log", "sources", "claim_evidence", "attachments", "ai_runs", "ai_proposals"]
# Settings keys that must never leave the machine (none hold secrets today; kept as a guard).
PRIVATE_SETTING_PREFIXES = ("secret", "credential")


def _columns(conn, table) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _dump(conn, table, where="", params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table} {where}", params).fetchall()]


# ---------------------------------------------------------------- full export / import

def export_all(conn) -> dict:
    tables = {t: _dump(conn, t) for t in ALL_TABLES}
    tables["settings"] = [s for s in tables["settings"] if not s["key"].startswith(PRIVATE_SETTING_PREFIXES)]
    return {"format": EXPORT_FORMAT, "format_version": FORMAT_VERSION, "schema_version": latest_version(),
            "app_version": config.APP_VERSION, "exported_at": now_iso(),
            "note": "Attachments are not embedded in this JSON export; use a backup (.zip) to include them.",
            "tables": tables}


def validate_export(doc: dict) -> None:
    if not isinstance(doc, dict) or doc.get("format") != EXPORT_FORMAT:
        raise ValidationError("This is not a Kindred Compass full export file")
    if int(doc.get("schema_version", 0)) > latest_version():
        raise ValidationError("This export comes from a newer version of the app")
    if not isinstance(doc.get("tables"), dict):
        raise ValidationError("Export file has no tables")
    unknown = set(doc["tables"]) - set(ALL_TABLES)
    if unknown:
        raise ValidationError(f"Unknown tables in export: {', '.join(sorted(unknown))}")


def import_all(conn, doc: dict) -> dict:
    """Replace ALL data with the export's contents (caller should back up first)."""
    validate_export(doc)
    counts = {}
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with Tx(conn):
            for t in reversed(ALL_TABLES):
                conn.execute(f"DELETE FROM {t}")
            for t in ALL_TABLES:
                rows_ = doc["tables"].get(t) or []
                cols = set(_columns(conn, t))
                for r in rows_:
                    if not isinstance(r, dict):
                        raise ValidationError(f"Bad row in {t}")
                    keep = {k: v for k, v in r.items() if k in cols}
                    if not keep:
                        continue
                    conn.execute(f"INSERT INTO {t} ({', '.join(keep)}) VALUES ({', '.join('?' for _ in keep)})", tuple(keep.values()))
                counts[t] = len(rows_)
            bad = conn.execute("PRAGMA foreign_key_check").fetchall()
            if bad:
                raise ValidationError(f"Import has {len(bad)} broken references; nothing was changed")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    return counts


# ---------------------------------------------------------------- project export / import

def export_project(conn, project_id: str, attachments_dir: Path | None = None, include_attachments: bool = True) -> dict:
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not proj:
        raise ValidationError("Project not found")
    tables = {}
    for t in PROJECT_TABLES:
        if t == "person_names":
            tables[t] = _dump(conn, t, "WHERE person_id IN (SELECT id FROM persons WHERE project_id = ?)", (project_id,))
        elif t == "claim_evidence":
            tables[t] = _dump(conn, t, "WHERE claim_id IN (SELECT id FROM claims WHERE project_id = ?)", (project_id,))
        else:
            tables[t] = _dump(conn, t, "WHERE project_id = ?", (project_id,))
    coll_ids = {r.get("collection_id") for t in ("tasks", "bookmarks", "research_log", "sources") for r in tables[t]} - {None}
    collection_refs = {}
    for cid in coll_ids:
        c = conn.execute("SELECT c.id, c.seed_key, c.name, p.name AS provider FROM collections c JOIN providers p ON p.id = c.provider_id WHERE c.id = ?", (cid,)).fetchone()
        if c:
            collection_refs[cid] = dict(c)
    files = {}
    if include_attachments and attachments_dir is not None:
        for a in tables["attachments"]:
            p = attachments_dir / a["stored_path"]
            if p.exists():
                files[a["id"]] = base64.b64encode(p.read_bytes()).decode()
    return {"format": PROJECT_FORMAT, "format_version": FORMAT_VERSION, "schema_version": latest_version(),
            "app_version": config.APP_VERSION, "exported_at": now_iso(), "project": dict(proj), "tables": tables,
            "collection_refs": collection_refs, "attachment_files": files}


ID_COLUMNS = {"id", "project_id", "person_id", "place_id", "to_place_id", "related_person_id", "question_id", "research_log_id",
              "duplicate_of_id", "claim_id", "source_id", "owner_id", "run_id"}


def import_project(conn, doc: dict, attachments_dir: Path, rename: str | None = None) -> dict:
    if not isinstance(doc, dict) or doc.get("format") != PROJECT_FORMAT:
        raise ValidationError("This is not a Kindred Compass project export")
    if int(doc.get("schema_version", 0)) > latest_version():
        raise ValidationError("This export comes from a newer version of the app")
    idmap: dict[str, str] = {}

    def remap(v):
        if v is None:
            return None
        if v not in idmap:
            idmap[v] = new_id()
        return idmap[v]

    # Resolve directory collections: same id, else same seed key, else drop the link (keeping the name as text).
    coll_map = {}
    for old, ref in (doc.get("collection_refs") or {}).items():
        hit = conn.execute("SELECT id FROM collections WHERE id = ?", (old,)).fetchone()
        if not hit and ref.get("seed_key"):
            hit = conn.execute("SELECT id FROM collections WHERE seed_key = ?", (ref["seed_key"],)).fetchone()
        coll_map[old] = (hit["id"] if hit else None, ref)

    proj = dict(doc["project"])
    new_pid = remap(proj["id"])
    ts = now_iso()
    files = doc.get("attachment_files") or {}
    written: list[Path] = []
    try:
        with Tx(conn):
            conn.execute("INSERT INTO projects (id, name, description, is_demo, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                         (new_pid, rename or proj.get("name") or "Imported project", proj.get("description"), int(proj.get("is_demo") or 0),
                          proj.get("created_at") or ts, ts))
            for t in PROJECT_TABLES:
                cols = set(_columns(conn, t))
                for r in doc["tables"].get(t) or []:
                    row = {k: v for k, v in r.items() if k in cols}
                    for k in list(row):
                        if k in ID_COLUMNS:
                            row[k] = remap(row[k])
                    if "collection_id" in row and row["collection_id"]:
                        mapped, ref = coll_map.get(r["collection_id"], (None, {}))
                        row["collection_id"] = mapped
                        if mapped is None and t == "research_log" and not row.get("resource_text"):
                            row["resource_text"] = f"{ref.get('name', 'Unknown collection')} ({ref.get('provider', '')})"
                    if t == "attachments":
                        old_id = r["id"]
                        ext = Path(r["stored_path"]).suffix
                        row["stored_path"] = f"{new_pid}/{row['id']}{ext}"
                        if old_id not in files:
                            continue
                        data = base64.b64decode(files[old_id])
                        if hashlib.sha256(data).hexdigest() != r["sha256"]:
                            raise ValidationError(f"Attachment {r.get('original_name')} failed its checksum")
                        dest = attachments_dir / row["stored_path"]
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(data)
                        written.append(dest)
                    conn.execute(f"INSERT INTO {t} ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", tuple(row.values()))
    except Exception:
        for p in written:
            p.unlink(missing_ok=True)
        raise
    return {"project_id": new_pid}


# ---------------------------------------------------------------- CSV

DIRECTORY_CSV_COLUMNS = ["provider", "name", "entry_kind", "repository_type", "url", "search_url", "description", "countries", "regions",
                         "counties", "dates", "record_types", "capabilities", "evidence_forms", "access_search", "access_images",
                         "access_copies", "integration_method", "search_link_verified", "verification_status", "last_verified",
                         "verification_source", "link_health", "limitations", "rights_notes", "archived", "origin", "seed_key"]


def directory_csv(conn) -> str:
    from .directory import all_collections
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(DIRECTORY_CSV_COLUMNS)
    for c in all_collections(conn, include_archived=True):
        geo = c.get("geo") or []
        w.writerow([c["provider_name"], c["name"], c["entry_kind"], c["repository_type"], c["url"], c["search_url"], c["description"],
                    "; ".join(sorted({g.get("country") for g in geo if g.get("country")})),
                    "; ".join(sorted({g.get("region") for g in geo if g.get("region")})),
                    "; ".join(sorted({g.get("county") for g in geo if g.get("county")})),
                    "; ".join(f"{r.get('from') or ''}-{r.get('to') or ''}" for r in c.get("dates") or []) or "unknown",
                    "; ".join(c.get("record_types") or []), "; ".join(c.get("capabilities") or []), "; ".join(c.get("evidence_forms") or []),
                    "; ".join(c.get("access_search") or []), "; ".join(c.get("access_images") or []), "; ".join(c.get("access_copies") or []),
                    c["integration_method"], "yes" if c["search_link_verified"] else "no", c["verification_status"], c["last_verified"],
                    c["verification_source"], c["link_health"], c["limitations"], c["rights_notes"] if c["rights_notes"] is not None else "unknown",
                    "yes" if c["archived"] else "no", c["origin"], c["seed_key"]])
    return _csv_safe(buf.getvalue())


LOG_CSV_COLUMNS = ["searched_on", "person", "question", "provider", "collection", "resource_text", "query", "name_variants", "filters",
                   "years", "place", "outcome", "coverage_notes", "access_notes", "result_url", "citation", "notes"]


def log_csv(conn, project_id: str) -> str:
    from .research_log import list_log
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(LOG_CSV_COLUMNS)
    for e in list_log(conn, project_id):
        w.writerow([e["searched_on"], e["person_name"], e["question_text"], e["provider_name"], e["collection_name"], e["resource_text"],
                    e["query_text"], "; ".join(e.get("name_variants") or []), e["filters_text"],
                    f"{e['year_from'] or ''}-{e['year_to'] or ''}" if (e["year_from"] or e["year_to"]) else "", e["place_text"], e["outcome"],
                    e["coverage_notes"], e["access_notes"], e["result_url"], e["citation_text"], e["notes"]])
    return _csv_safe(buf.getvalue())


def _csv_safe(text: str) -> str:
    """Neutralise spreadsheet formula injection: prefix cells starting with = + - @ with a quote."""
    out = io.StringIO()
    w = csv.writer(out)
    for row in csv.reader(io.StringIO(text)):
        w.writerow(["'" + c if c[:1] in ("=", "+", "-", "@") and not c[:2].lstrip("-").isdigit() else c for c in row])
    return out.getvalue()


# ---------------------------------------------------------------- backup / restore

def create_backup(settings: config.Settings, label: str = "manual") -> Path:
    ts = now_iso().replace(":", "").replace("+0000", "Z")
    dest = settings.backups_dir / f"kindred-backup-{ts}-{label}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "kindred.sqlite3"
        src = connect(settings.db_path)
        try:
            dst = sqlite3.connect(snap)
            src.backup(dst)
            dst.close()
        finally:
            src.close()
        manifest = {"format": BACKUP_FORMAT, "format_version": FORMAT_VERSION, "schema_version": latest_version(),
                    "app_version": config.APP_VERSION, "created_at": now_iso(), "files": {}}
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "kindred.sqlite3")
            manifest["files"]["kindred.sqlite3"] = _sha(snap)
            for base, prefix in ((settings.attachments_dir, "attachments/"), (settings.imports_dir, "imports/")):
                for f in sorted(base.rglob("*")):
                    if f.is_file() and not f.is_symlink():
                        arc = prefix + f.relative_to(base).as_posix()
                        z.write(f, arc)
                        manifest["files"][arc] = _sha(f)
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
    return dest


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def restore_backup(settings: config.Settings, zip_path: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        try:
            z = zipfile.ZipFile(zip_path)
        except zipfile.BadZipFile:
            raise ValidationError("Not a valid backup archive")
        with z:
            names = z.namelist()
            if "manifest.json" not in names or "kindred.sqlite3" not in names:
                raise ValidationError("Backup is missing its manifest or database")
            for n in names:
                if n.startswith("/") or ".." in Path(n).parts or "\\" in n:
                    raise ValidationError("Backup contains unsafe paths")
                if not (n in ("manifest.json", "kindred.sqlite3") or n.startswith(("attachments/", "imports/"))):
                    raise ValidationError(f"Unexpected file in backup: {n}")
            manifest = json.loads(z.read("manifest.json"))
            if manifest.get("format") != BACKUP_FORMAT:
                raise ValidationError("Not a Kindred Compass backup")
            if int(manifest.get("schema_version", 0)) > latest_version():
                raise ValidationError("Backup comes from a newer version of the app")
            z.extractall(tmpd)
        for name, digest in manifest["files"].items():
            p = tmpd / name
            if not p.exists() or _sha(p) != digest:
                raise ValidationError(f"Backup file failed its checksum: {name}")
        check = sqlite3.connect(tmpd / "kindred.sqlite3")
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValidationError("Backup database failed its integrity check")
        finally:
            check.close()

        safety = create_backup(settings, "pre-restore")
        # Replace database contents in place with SQLite's online backup API.
        src = sqlite3.connect(tmpd / "kindred.sqlite3")
        dst = connect(settings.db_path)
        try:
            src.backup(dst)
            migrate(dst, settings.db_path)
        finally:
            src.close()
            dst.close()
        # Replace attachments and import folders.
        for name, target in (("attachments", settings.attachments_dir), ("imports", settings.imports_dir)):
            src_dir = tmpd / name
            if target.exists():
                shutil.rmtree(target)
            if src_dir.exists():
                shutil.copytree(src_dir, target)
            else:
                target.mkdir(parents=True, exist_ok=True)
    return {"restored_from": zip_path.name, "safety_backup": safety.name, "schema_version": manifest.get("schema_version")}


def list_backups(settings: config.Settings) -> list[dict]:
    return [{"name": p.name, "size_bytes": p.stat().st_size} for p in sorted(settings.backups_dir.glob("*.zip"), reverse=True)]
