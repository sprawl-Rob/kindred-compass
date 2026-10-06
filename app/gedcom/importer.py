"""GEDCOM import lifecycle: stage → preview → commit → (review) → undo.

* A first import always goes into a new, separate project (a *lineage* = one originating tree).
* Repeat imports of the same tree reuse the lineage. Identifiers (xrefs, _UID, RIN) are only
  compared within that lineage and are never assumed to be globally stable: an xref match also
  needs a compatible name and birth window; anything doubtful goes to the review queue and is
  imported separately rather than merged.
* Facts already imported are recognised by fingerprint and not duplicated; facts that vanished
  from the new export are flagged, not deleted; rows you edited locally are never overwritten.
* Imported claims are "working" claims with origin = import — never marked verified.
* Every created row is linked to the GEDCOM lines it came from (side-by-side inspection) and
  recorded in import_changes so the batch can be undone.
* Importing is a snapshot. Nothing is synchronised with Ancestry, and remote media is never fetched.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import date
from pathlib import Path

from .. import attachments as att
from .. import evidence as ev
from .. import portability as port
from ..db import Tx, insert, new_id, now_iso, one, rows, update
from ..directory import NotFound, ValidationError
from . import media as md
from .model import Model, Person, build, node_json, subtree_hash, summarize_unsupported, summarize_vendor
from .parser import GedcomFile, detect_product, parse_bytes

QUAY = {"0": "unreliable evidence or estimated data", "1": "questionable reliability", "2": "secondary evidence",
        "3": "direct and primary evidence"}
GEDCOM_EXT = (".ged", ".gedcom")
ARCHIVE_EXT = (".zip", ".gdz")
SNAPSHOT_NOTE = ("This is a one-time snapshot of the exported file. It is not connected to Ancestry and will not "
                 "update automatically; to bring in later changes, export again and run a repeat import.")


# ======================================================================= staging & preview

def imports_dir(settings) -> Path:
    d = settings.data_dir / "imports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stage(conn, settings, upload_path: Path, upload_name: str, media_uploads: list[tuple[str, Path]], target_lineage_id: str | None,
          project_name: str | None, member: str | None = None) -> dict:
    """Store the original upload, extract archives safely, and compute the preview plan."""
    name = att.safe_name(upload_name or "upload.ged")
    low = name.lower()
    if not low.endswith(GEDCOM_EXT + ARCHIVE_EXT):
        raise ValidationError("Choose a GEDCOM file (.ged) or a ZIP archive containing one (.zip / .gdz).")
    if target_lineage_id:
        one_or_404(conn, "SELECT * FROM import_lineages WHERE id = ?", target_lineage_id, "earlier import")
    bid = new_id()
    root = imports_dir(settings) / bid
    (root / "original").mkdir(parents=True)
    (root / "media").mkdir()
    original = root / "original" / name
    shutil.copyfile(upload_path, original)
    sha = sha256_file(original)
    media_info = {"sources": [], "skipped": [], "gedcom_archive_members": []}
    try:
        if low.endswith(ARCHIVE_EXT):
            members = md.list_zip(original)
            geds = [m for m in members if m.lower().endswith(GEDCOM_EXT) and md.safe_relpath(m) and not md.is_ignored(md.safe_relpath(m))]
            if not geds:
                raise ValidationError("The archive does not contain a .ged file.")
            media_info["gedcom_archive_members"] = geds
            chosen = member if member in geds else sorted(geds, key=lambda x: (x.count("/"), x))[0]
            res = md.safe_extract(original, root / "media")
            media_info["skipped"] += res["skipped"]
            media_info["sources"].append({"kind": "archive with GEDCOM", "name": name, "files": len(res["files"])})
            ged_path = root / "media" / md.safe_relpath(chosen)
            gedcom_member = chosen
        else:
            ged_path, gedcom_member = original, None
        _add_media(root, media_uploads, media_info)
        data = ged_path.read_bytes()
    except (md.ArchiveError, ValidationError) as e:
        shutil.rmtree(root, ignore_errors=True)
        raise ValidationError(str(e))
    g = parse_bytes(data)
    if g.head is None and not g.records:
        shutil.rmtree(root, ignore_errors=True)
        raise ValidationError("This file does not look like GEDCOM (no HEAD or records found).")
    det = detect_product(g.head)
    with Tx(conn):
        insert(conn, "import_batches", {
            "id": bid, "lineage_id": target_lineage_id, "status": "previewed", "original_filename": name, "stored_dir": bid,
            "gedcom_member": gedcom_member, "sha256": sha, "product": det["product"], "gedcom_version": g.version, "encoding": g.encoding,
            "detection_json": json.dumps({**det, "declared_charset": g.declared_charset, "line_count": g.line_count,
                                          "project_name": project_name}),
            "media_json": json.dumps(media_info), "created_at": now_iso()})
    return replan(conn, settings, bid)


def _add_media(root: Path, media_uploads: list[tuple[str, Path]], info: dict) -> None:
    folder_files = 0
    for rel, path in media_uploads:
        if rel.lower().endswith(".zip"):
            res = md.safe_extract(path, root / "media")
            info["skipped"] += res["skipped"]
            info["sources"].append({"kind": "media archive", "name": att.safe_name(rel), "files": len(res["files"])})
            continue
        safe = md.safe_relpath(rel)
        if safe is None or md.is_ignored(safe):
            if safe is None:
                info["skipped"].append({"name": rel, "reason": "unsafe path"})
            continue
        dest = (root / "media" / safe).resolve()
        if (root / "media").resolve() not in dest.parents:
            info["skipped"].append({"name": rel, "reason": "path escapes the import folder"})
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        folder_files += 1
    if folder_files:
        info["sources"].append({"kind": "media folder", "name": "uploaded folder", "files": folder_files})


def add_media(conn, settings, batch_id: str, media_uploads: list[tuple[str, Path]]) -> dict:
    b = get_batch_row(conn, batch_id)
    if b["status"] != "previewed":
        raise ValidationError("Media can only be added before the import is committed.")
    root = imports_dir(settings) / b["stored_dir"]
    info = b["media"]
    try:
        _add_media(root, media_uploads, info)
    except md.ArchiveError as e:
        raise ValidationError(str(e))
    update(conn, "import_batches", batch_id, {"media_json": json.dumps(info)})
    return replan(conn, settings, batch_id)


def load(settings, b: dict) -> tuple[GedcomFile, Model, Path]:
    root = imports_dir(settings) / b["stored_dir"]
    path = (root / "media" / md.safe_relpath(b["gedcom_member"])) if b["gedcom_member"] else (root / "original" / b["original_filename"])
    g = parse_bytes(path.read_bytes())
    return g, build(g), root


def replan(conn, settings, batch_id: str) -> dict:
    b = get_batch_row(conn, batch_id)
    g, m, root = load(settings, b)
    det = detect_product(g.head)
    update(conn, "import_batches", batch_id, {
        "product": det["product"], "gedcom_version": g.version, "encoding": g.encoding,
        "detection_json": json.dumps({**det, "declared_charset": g.declared_charset, "line_count": g.line_count,
                                      "project_name": (b["detection"] or {}).get("project_name")})})
    b = get_batch_row(conn, batch_id)
    files = md.inventory(root / "media")
    ged_rel = md.safe_relpath(b["gedcom_member"]) if b["gedcom_member"] else None
    files = [f for f in files if f != ged_rel]
    plan = make_plan(conn, b, g, m, files)
    update(conn, "import_batches", batch_id, {"plan_json": json.dumps(plan, ensure_ascii=False, default=str)})
    return get_batch(conn, batch_id)


def media_match(ref: dict, files: list[str]) -> dict:
    """Match one media reference; Ancestry media records carry no file, only an online id."""
    if not ref["file"] and ref.get("oid"):
        kind = f" ({ref['media_type']})" if ref.get("media_type") else ""
        how = f"Held on Ancestry{kind}, media id {ref['oid']}; the export does not include the file."
        if (ref.get("media_type") or "").lower() == "story":
            how += " Stories appear in exports as an empty placeholder."
        return {"status": "not_in_export", "path": None, "candidates": [], "how": how}
    return md.match_reference(ref["file"], files)


def relationships(m: Model) -> list[dict]:
    out = []
    for f in m.families.values():
        if f.husb and f.wife:
            out.append({"kind": "spouse", "a": f.husb, "b": f.wife, "fam": f.xref, "qualifier": None})
        for c in f.children:
            pedi = {}
            child = m.people.get(c["xref"])
            if child:
                for fx, q, raw in child.famc:
                    if fx == f.xref:
                        pedi = {"q": q, "raw": raw}
            for role, parent in (("father", f.husb), ("mother", f.wife)):
                if not parent:
                    continue
                q = c["frel"] if role == "father" else c["mrel"]
                raw = c["raw_frel"] if role == "father" else c["raw_mrel"]
                if not raw and pedi.get("raw"):
                    q, raw = pedi["q"], pedi["raw"]
                out.append({"kind": "child", "child": c["xref"], "parent": parent, "role": role, "fam": f.xref,
                            "qualifier": q or ("other" if raw else None), "raw": raw})
    return out


def make_plan(conn, b: dict, g: GedcomFile, m: Model, files: list[str]) -> dict:
    rels = relationships(m)
    qual = {}
    for r in rels:
        if r["kind"] == "child":
            k = r["qualifier"] or "not stated"
            qual[k] = qual.get(k, 0) + 1
    facts = sum(len(p.facts) for p in m.people.values()) + sum(len(f.facts) for f in m.families.values())
    names = sum(len(p.names) for p in m.people.values())
    notes = sum(len(p.notes) for p in m.people.values()) + sum(len(f.notes) for f in m.families.values()) + \
        sum(len(fa.notes) for p in m.people.values() for fa in p.facts)
    media_plan = []
    for ref in m.media_refs:
        res = media_match(ref, files)
        status = res["status"]
        if status == "matched":
            ext = Path(res["path"]).suffix.lower()
            if ext not in att.ALLOWED:
                status = "unsupported_type"
        if status == "missing" and not files and not md.is_remote(ref["file"]) and ref["file"]:
            status = "not_supplied"
        media_plan.append({"file_ref": ref["file"], "owner_kind": ref["owner_kind"], "owner_xref": ref["owner_xref"],
                           "title": ref["title"], "obje": ref["obje_xref"], "line": ref["line"], "status": status,
                           "path": res["path"], "candidates": res["candidates"], "how": res["how"]})
    referenced = {mp["path"] for mp in media_plan if mp["path"]}
    for mp in media_plan:
        referenced.update(mp["candidates"])
    unreferenced = [f for f in files if f not in referenced]
    counts = {
        "people": len(m.people), "families": len(m.families),
        "relationships_parent_child": sum(1 for r in rels if r["kind"] == "child"),
        "relationships_partner": sum(1 for r in rels if r["kind"] == "spouse"),
        "events_and_facts": facts, "names": names, "sources": len(m.sources), "citations": len(m.citations),
        "repositories": len(m.repositories), "notes": notes + len(m.notes),
        "media_references": len(m.media_refs),
        "media_local_refs": sum(1 for r in m.media_refs if r["file"] and not md.is_remote(r["file"])),
        "media_remote_refs": sum(1 for r in m.media_refs if md.is_remote(r["file"]) or (not r["file"] and r.get("oid"))),
        "supplied_files": len(files),
        "parse_failures": len(g.failures),
        "ancestry_record_ids": sum(1 for c in m.citations.values() if c.apid) + sum(1 for s in m.sources.values() if s["apid"]),
    }
    media_summary = {}
    for mp in media_plan:
        media_summary[mp["status"]] = media_summary.get(mp["status"], 0) + 1
    det = b["detection"]
    plan = {
        "snapshot_note": SNAPSHOT_NOTE,
        "detection": {"product": b["product"], "product_label": PRODUCT_LABEL.get(b["product"], "Other GEDCOM"),
                      "source": det.get("source"), "source_name": det.get("source_name"), "source_version": det.get("source_version"),
                      "tree_name": det.get("tree_name"), "tree_id": det.get("tree_id"), "tree_description": det.get("tree_description"),
                      "export_date": det.get("export_date"),
                      "gedcom_version": g.version or "not stated", "encoding": g.encoding, "declared_charset": g.declared_charset,
                      "lines": g.line_count, "trailer": g.trailer_seen, "gedcom_member": b["gedcom_member"],
                      "archive_members": b["media"].get("gedcom_archive_members", [])},
        "counts": counts, "relationship_qualifiers": qual,
        "warnings": g.warnings + m.warnings[:200] + ([f"{len(m.warnings) - 200} more warnings not shown"] if len(m.warnings) > 200 else []),
        "unsupported": summarize_unsupported(m),
        "vendor_tags_mapped": summarize_vendor(m),
        "failures": g.failures[:500],
        "media": {"summary": media_summary, "items": media_plan[:2000], "unreferenced_supplied": unreferenced[:500],
                  "unreferenced_count": len(unreferenced), "skipped": b["media"].get("skipped", []), "sources": b["media"].get("sources", [])},
        "profiles": profiles(m, rels),
        "export_contents": export_contents(b["product"], counts, m),
    }
    plan["repeat"] = repeat_plan(conn, b, m) if b["lineage_id"] else None
    return plan


PRODUCT_LABEL = {"ancestry": "Ancestry.com family tree export", "ftm": "Family Tree Maker export", "rootsmagic": "RootsMagic export",
                 "other": "GEDCOM from another program"}


def export_contents(product: str, counts: dict, m: Model) -> dict:
    """What this particular file contains, and what an Ancestry export does not carry."""
    present = [k for k in ("people", "families", "events_and_facts", "sources", "citations", "notes", "repositories", "media_references")
               if counts.get(k)]
    out = {"present": present,
           "local_media_files_in_export": counts["supplied_files"],
           "remote_media_references": counts["media_remote_refs"]}
    if product == "ancestry":
        out["not_in_export"] = ANCESTRY_NOT_EXPORTED
    return out


# From Ancestry's help pages and real exports (see tools/research/gedcom_exports.md and docs/ancestry-import.md).
ANCESTRY_NOT_EXPORTED = [
    "Photos, documents and other media files. Ancestry: “photos, media, and similar items are not included.” Media appear only as "
    "records with an Ancestry media id and an empty file reference.",
    "Uploaded stories: they appear only as empty media placeholders.",
    "Record images from Ancestry collections: citations carry an Ancestry record reference (_APID), not the image.",
    "DNA results and matches. Raw DNA data is a separate download from DNA Settings; Ancestry states that DNA match lists cannot be "
    "downloaded or exported. ThruLines and ethnicity estimates are DNA features and are not in the tree export.",
    "Hints, comments and member messages: Ancestry does not document them as exported, and they do not appear in exports we examined.",
    "Living people are exported in full (Ancestry's export has no privacy option); Kindred Compass treats people without a recorded "
    "death as possibly living and keeps them private.",
]


def profiles(m: Model, rels: list[dict], limit: int = 6) -> list[dict]:
    """Representative people to check after import, each chosen for a reason."""
    people = list(m.people.values())
    if not people:
        return []
    parents_of: dict = {}
    for r in rels:
        if r["kind"] == "child":
            parents_of.setdefault(r["child"], []).append(r)
    chosen, why = [], {}

    def pick(pred, reason):
        for p in chosen:          # an already-chosen person may illustrate several things
            if pred(p):
                why[p.xref].append(reason)
                return
        for p in people:
            if p.xref not in why and pred(p):
                chosen.append(p)
                why[p.xref] = [reason]
                return

    pick(lambda p: True, "First person in the file (often the tree's home person)")
    pick(lambda p: len(p.fams) > 1, "Has more than one marriage or partnership")
    pick(lambda p: any((r["qualifier"] or "biological") not in ("biological",) for r in parents_of.get(p.xref, [])),
         "Has a non-biological or unstated parent relationship")
    pick(lambda p: any(f.date["date_qualifier"] not in ("exact", "unknown") for f in p.facts), "Has approximate or uncertain dates")
    pick(lambda p: any(ord(ch) > 127 for n in p.names for ch in (n.full + n.given + n.surname)), "Name contains non-ASCII characters")
    pick(lambda p: any(sum(1 for g in p.facts if g.tag == t) > 1 for t in ("BIRT", "DEAT", "CHR", "BURI")), "Has alternative (conflicting) facts")
    pick(lambda p: bool(p.media), "Has media references")
    most = max(len(x.facts) + len(x.citations) for x in people)
    pick(lambda p: len(p.facts) + len(p.citations) == most, "Most facts and citations")
    out = []
    for p in chosen[:limit + 2]:
        out.append({
            "xref": p.xref, "name": p.display_name, "why": "; ".join(why[p.xref]), "reasons": why[p.xref], "sex": p.sex,
            "names": [{"type": n.name_type, "text": n.full or f"{n.given} {n.surname}".strip()} for n in p.names],
            "facts": [{"label": f.label, "date": f.date_text, "qualifier": f.date["date_qualifier"], "place": (f.place or {}).get("name"),
                       "value": f.value, "citations": len(f.citations), "line": f.node.line} for f in p.facts],
            "parents": [{"parent": m.people[r["parent"]].display_name if r["parent"] in m.people else r["parent"], "role": r["role"],
                         "qualifier": r["qualifier"] or "not stated", "raw": r["raw"]} for r in parents_of.get(p.xref, [])],
            "partners": len(p.fams), "media": len(p.media), "notes": len(p.notes),
            "original_lines": p.node.lines()[:80]})
    return out


# ======================================================================= repeat-import matching

def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower().strip()


def _identity(p: Person) -> dict:
    n = p.names[0] if p.names else None
    birth = next((f for f in p.facts if f.claim_type in ("birth", "baptism") and f.date["year_from"] is not None), None)
    return {"surname": _norm(n.surname if n else ""), "given": _norm((n.given if n else "").split(" ")[0] if n else ""),
            "birth": (birth.date["year_from"], birth.date["year_to"]) if birth else None, "name": p.display_name}


def _compatible(a: dict, b: dict) -> tuple[bool, list[str]]:
    reasons = []
    ok = True
    if a["surname"] != b["surname"]:
        ok = False
        reasons.append(f"surname differs ({a['surname'] or '—'} vs {b['surname'] or '—'})")
    if a["given"] and b["given"] and a["given"] != b["given"] and a["given"][:1] != b["given"][:1]:
        ok = False
        reasons.append(f"given name differs ({a['given']} vs {b['given']})")
    if a["birth"] and b["birth"] and not (a["birth"][0] <= b["birth"][1] + 2 and b["birth"][0] <= a["birth"][1] + 2):
        ok = False
        reasons.append(f"birth years differ ({a['birth'][0]} vs {b['birth'][0]})")
    return ok, reasons


def match_people(conn, lineage_id: str, m: Model) -> dict:
    """Classify each person in the new file against what this lineage imported before."""
    existing = rows(conn, "SELECT * FROM import_records WHERE lineage_id = ? AND record_type = 'INDI'", (lineage_id,))
    by_xref = {r["xref"]: r for r in existing}
    by_key: dict = {}
    for r in existing:
        for k in r["stable_keys"] or []:
            if not k.startswith("distinct:"):
                by_key.setdefault(k, []).append(r)
    used: set = set()
    result = {}
    for p in m.people.values():
        ident = _identity(p)
        hit, how = None, None
        for k in p.stable_keys:
            cands = [r for r in by_key.get(k, []) if r["id"] not in used]
            if len(cands) == 1:
                hit, how = cands[0], f"same stable identifier ({k.split(':')[0]})"
                break
        if hit is None and p.xref in by_xref and by_xref[p.xref]["id"] not in used:
            r = by_xref[p.xref]
            prev_ident = r["raw"]["_identity"] if "_identity" in r["raw"] else None
            ok, reasons = _compatible(ident, prev_ident) if prev_ident else (True, [])
            if ok:
                hit, how = r, "same record identifier within this tree, consistent name and birth"
            else:
                result[p.xref] = {"status": "uncertain", "candidate": r, "likely_same": False,
                                  "reasons": [f"same identifier {p.xref} but " + "; ".join(reasons)]}
                continue
        if hit is None:
            # Heuristic suggestion only (never auto-merged)
            cands = []
            for r in existing:
                if r["id"] in used:
                    continue
                prev = r["raw"].get("_identity")
                if prev and ident["surname"] and ident["birth"] and prev.get("birth"):
                    ok, _ = _compatible(ident, prev)
                    if ok and ident["given"] == prev["given"]:
                        cands.append(r)
            if len(cands) == 1:
                result[p.xref] = {"status": "uncertain", "candidate": cands[0], "likely_same": True,
                                  "reasons": ["different identifier, but same name and compatible birth year"]}
                continue
            result[p.xref] = {"status": "new"}
            continue
        used.add(hit["id"])
        changed = hit["content_hash"] != subtree_hash(p.node)
        result[p.xref] = {"status": "changed" if changed else "unchanged", "record": hit, "how": how}
    seen = {v["record"]["id"] for v in result.values() if v.get("record")}
    likely = {v["candidate"]["id"] for v in result.values() if v.get("candidate") and v.get("likely_same")}
    missing = [r for r in existing if r["id"] not in seen and r["id"] not in likely]
    return {"people": result, "missing": missing}


def repeat_plan(conn, b: dict, m: Model) -> dict:
    lin = one(conn, "SELECT * FROM import_lineages WHERE id = ?", (b["lineage_id"],))
    mp = match_people(conn, b["lineage_id"], m)
    stats = {"unchanged": 0, "changed": 0, "new": 0, "uncertain": 0}
    uncertain = []
    for x, v in mp["people"].items():
        stats[v["status"]] += 1
        if v["status"] == "uncertain":
            uncertain.append({"xref": x, "name": m.people[x].display_name, "candidate": v["candidate"]["raw"].get("_identity", {}).get("name"),
                              "reasons": v["reasons"]})
    det = b["detection"]
    tree_key = make_tree_key(b["product"], det)
    return {"lineage_id": b["lineage_id"], "lineage_label": lin and lin["tree_label"], "stats": stats, "uncertain": uncertain[:200],
            "missing_from_export": [r["raw"].get("_identity", {}).get("name") for r in mp["missing"]][:200],
            "missing_count": len(mp["missing"]),
            "tree_key_matches": bool(lin) and lin["tree_key"] == tree_key,
            "note": "Records are matched only within this tree's import history. Uncertain matches are imported separately and listed for review — nothing is merged automatically."}


def make_tree_key(product: str, det: dict) -> str:
    return "|".join([product or "other", (det.get("tree_id") or "").strip(), (det.get("tree_name") or det.get("file_name") or "").strip().lower()])


# ======================================================================= commit

class Writer:
    """Inserts rows, records them for undo, and links them to their GEDCOM origin."""

    def __init__(self, conn, batch: dict, lineage_id: str, project_id: str, label: str):
        self.conn, self.batch, self.lineage_id, self.project_id, self.label = conn, batch, lineage_id, project_id, label
        self.ts = now_iso()
        self.places: dict = {}
        self.stats: dict = {}
        self.snapshot = date.today().isoformat()
        self.model_sources: dict = {}
        self.media_done: set = set()

    def bump(self, k, n=1):
        self.stats[k] = self.stats.get(k, 0) + n

    def created(self, table: str, row_id: str):
        self.conn.execute("INSERT INTO import_changes (batch_id, table_name, row_id, before_json, created_at) VALUES (?,?,?,?,?)",
                          (self.batch["id"], table, row_id, None, self.ts))

    def changed(self, table: str, row: dict):
        self.conn.execute("INSERT INTO import_changes (batch_id, table_name, row_id, before_json, created_at) VALUES (?,?,?,?,?)",
                          (self.batch["id"], table, row["id"], json.dumps(row, default=str), self.ts))

    def ins(self, table: str, values: dict) -> str:
        rid = values.get("id") or new_id()
        insert(self.conn, table, {"id": rid, **values})
        self.created(table, rid)
        return rid

    def link(self, entity_type: str, entity_id: str, anchor: str | None, fact_key: str | None, nodes) -> None:
        nodes = nodes if isinstance(nodes, list) else [nodes]
        lid = new_id()
        insert(self.conn, "import_links", {"id": lid, "batch_id": self.batch["id"], "lineage_id": self.lineage_id, "entity_type": entity_type,
                                           "entity_id": entity_id, "record_xref": anchor, "fact_key": fact_key,
                                           "gedcom_json": json.dumps([n if isinstance(n, dict) else node_json(n) for n in nodes], ensure_ascii=False),
                                           "imported_at": self.ts})
        self.created("import_links", lid)

    def place(self, p: dict | None) -> str | None:
        if not p or not p.get("name"):
            return None
        key = p["name"]
        if key in self.places:
            return self.places[key]
        hit = one(self.conn, "SELECT id FROM places WHERE project_id = ? AND name = ?", (self.project_id, key))
        if hit:
            self.places[key] = hit["id"]
            return hit["id"]
        pid = self.ins("places", {"project_id": self.project_id, "name": key, "country": p.get("country"), "region": p.get("region"),
                                  "county": p.get("county"), "municipality": p.get("municipality"),
                                  "jurisdiction_notes": "Imported place name; jurisdiction fields split automatically from the original text"
                                  + (f"; map {p.get('lat')}, {p.get('long')}" if p.get("lat") else ""),
                                  "created_at": self.ts, "updated_at": self.ts})
        self.places[key] = pid
        return pid


def get_lineage_project(conn, lineage_id):
    lin = one(conn, "SELECT * FROM import_lineages WHERE id = ?", (lineage_id,))
    if not lin:
        raise NotFound("import lineage")
    return lin


def commit(conn, settings, batch_id: str) -> dict:
    b = get_batch_row(conn, batch_id)
    if b["status"] != "previewed":
        raise ValidationError(f"This import is {b['status']}; only a previewed import can be committed.")
    t0 = time.monotonic()
    safety = port.create_backup(settings, "pre-import")
    g, m, root = load(settings, b)
    det = b["detection"]
    label = f"{PRODUCT_LABEL.get(b['product'], 'GEDCOM')} “{det.get('tree_name') or b['original_filename']}”"
    snapshot_date = date.today().isoformat()
    written_files: list = []
    try:
        with Tx(conn):
            if b["lineage_id"]:
                lin = get_lineage_project(conn, b["lineage_id"])
                project_id, lineage_id, created_project = lin["project_id"], lin["id"], False
            else:
                project_id, lineage_id, created_project = new_id(), new_id(), True
                name = det.get("project_name") or f"Imported: {det.get('tree_name') or b['original_filename']} ({snapshot_date} snapshot)"
                insert(conn, "projects", {"id": project_id, "name": name[:200], "is_demo": 0, "import_lineage_id": lineage_id,
                                          "description": f"{label} imported {snapshot_date}. {SNAPSHOT_NOTE}",
                                          "created_at": now_iso(), "updated_at": now_iso()})
                insert(conn, "import_lineages", {"id": lineage_id, "project_id": project_id, "product": b["product"] or "other",
                                                 "tree_label": det.get("tree_name") or b["original_filename"],
                                                 "tree_key": make_tree_key(b["product"], det), "created_at": now_iso()})
            update(conn, "import_batches", batch_id, {"lineage_id": lineage_id, "project_id": project_id})
            b = get_batch_row(conn, batch_id)
            w = Writer(conn, b, lineage_id, project_id, label)
            w.snapshot = snapshot_date
            w.model_sources = m.sources
            report = apply_model(conn, settings, w, g, m, root, written_files)
            report.update({"safety_backup": safety.name, "created_project": created_project, "project_id": project_id,
                           "lineage_id": lineage_id, "elapsed_seconds": round(time.monotonic() - t0, 2),
                           "failures": g.failures, "warnings": g.warnings + m.warnings, "unsupported": summarize_unsupported(m),
                           "snapshot_note": SNAPSHOT_NOTE, "checked_at": None, "detection": b["plan"].get("detection"),
                           "export_contents": b["plan"].get("export_contents")})
            update(conn, "import_batches", batch_id, {"status": "committed", "committed_at": now_iso(), "created_project": int(created_project),
                                                     "report_json": json.dumps(report, ensure_ascii=False, default=str)})
    except Exception:
        for f in written_files:
            Path(f).unlink(missing_ok=True)
        raise
    return get_batch(conn, batch_id)


def _status_note(w: Writer, extra: str = "") -> str:
    return (f"Imported from {w.label} on {w.snapshot}. Recorded in the tree; not independently verified." + (" " + extra if extra else "")).strip()


def apply_model(conn, settings, w: Writer, g: GedcomFile, m: Model, root: Path, written_files: list) -> dict:
    repeat = bool(w.batch["lineage_id"]) and one(conn, "SELECT COUNT(*) AS n FROM import_records WHERE lineage_id = ?", (w.lineage_id,))["n"] > 0
    matches = match_people(conn, w.lineage_id, m) if repeat else {"people": {x: {"status": "new"} for x in m.people}, "missing": []}
    person_ids: dict = {}
    anchors: dict = {}

    # ---- people
    for p in m.people.values():
        mt = matches["people"][p.xref]
        ident = _identity(p)
        raw = {**node_json(p.node), "_identity": ident}
        mapped = {"display_name": p.display_name[:300], "sex": p.sex, "notes": "\n\n".join(p.notes) or None}
        if mt["status"] in ("unchanged", "changed"):
            rec = mt["record"]
            pid = rec["entity_id"]
            if not one(conn, "SELECT id FROM persons WHERE id = ?", (pid,)):
                mt = {"status": "new"}   # the person was deleted locally since the last import → re-create
            else:
                w.changed("import_records", rec)
                update(conn, "import_records", rec["id"], {"xref": p.xref, "stable_keys_json": json.dumps(sorted(set(p.stable_keys) | set(rec["stable_keys"] or []))),
                                                           "content_hash": subtree_hash(p.node), "raw_json": json.dumps(raw, ensure_ascii=False),
                                                           "last_batch_id": w.batch["id"], "updated_at": w.ts})
                person_ids[p.xref], anchors[p.xref] = pid, rec["id"]
                if mt["status"] == "unchanged":
                    w.bump("people_unchanged")
                    continue
                w.bump("people_updated")
                _update_person_fields(conn, w, pid, rec, mapped)
        if mt["status"] in ("new", "uncertain"):
            pid = w.ins("persons", {"project_id": w.project_id, "display_name": mapped["display_name"], "sex": p.sex,
                                    "living_status": p.living_hint, "is_private": 1, "notes": mapped["notes"], "origin": "import",
                                    "created_at": w.ts, "updated_at": w.ts})
            rid = w.ins("import_records", {"lineage_id": w.lineage_id, "record_type": "INDI", "xref": p.xref,
                                           "stable_keys_json": json.dumps(p.stable_keys), "entity_type": "person", "entity_id": pid,
                                           "content_hash": subtree_hash(p.node), "raw_json": json.dumps(raw, ensure_ascii=False),
                                           "first_batch_id": w.batch["id"], "last_batch_id": w.batch["id"], "created_at": w.ts, "updated_at": w.ts})
            w.link("person", pid, rid, "person", {**node_json(p.node), "children": [], "_mapped": mapped})
            person_ids[p.xref], anchors[p.xref] = pid, rid
            w.bump("people_created")
            if mt["status"] == "uncertain":
                cand = mt["candidate"]
                review(conn, w, "uncertain_match", p.xref, "person", pid,
                       f"{p.display_name} ({p.xref}) may be the same person as “{(cand['raw'] or {}).get('_identity', {}).get('name')}” from an earlier import. Imported separately.",
                       {"existing_person_id": cand["entity_id"], "existing_record_id": cand["id"], "new_record_id": rid, "reasons": mt["reasons"]})
                w.bump("people_uncertain")
    # people present before but missing now
    for r in matches["missing"]:
        if one(conn, "SELECT id FROM persons WHERE id = ?", (r["entity_id"],)):
            review(conn, w, "removed_in_source", r["xref"], "person", r["entity_id"],
                   f"“{(r['raw'] or {}).get('_identity', {}).get('name')}” was in an earlier import but is not in this export. Kept unchanged.", {})
            w.bump("people_missing_from_export")

    # ---- names & facts
    seen_links = _existing_fact_keys(conn, w.lineage_id)
    cite_sources = _existing_cite_sources(conn, w.lineage_id)
    current_by_anchor: dict = {}
    for p in m.people.values():
        pid, anchor = person_ids[p.xref], anchors[p.xref]
        for n in p.names:
            if (anchor, n.key) in seen_links:
                continue
            nid = w.ins("person_names", {"person_id": pid, "name_type": n.name_type, "given": n.given or None, "surname": n.surname or None,
                                         "full_text": n.full or None, "script": n.script, "language": n.language,
                                         "note": "; ".join(x for x in [n.note, n.prefix and f"prefix {n.prefix}", n.suffix and f"suffix {n.suffix}"] if x) or None,
                                         "origin": "import", "created_at": w.ts})
            w.link("name", nid, anchor, n.key, n.node)
            seen_links.add((anchor, n.key))
            w.bump("names_added")
        current_keys = {n.key for n in p.names}
        for f in p.facts:
            current_keys.add(f.key)
            if (anchor, f.key) in seen_links:
                w.bump("facts_already_imported")
                continue
            cid = _fact_claim(conn, w, pid, f, None)
            w.link("claim", cid, anchor, f.key, f.node)
            seen_links.add((anchor, f.key))
            _cite(conn, w, cid, f.citations, cite_sources)
            _attach_media(conn, settings, w, f.media, "person", pid, root, written_files)
        idcites = list(p.citations) + [c for n in p.names for c in n.citations]
        if idcites:
            key = "identity"
            current_keys.add(key)
            if (anchor, key) not in seen_links:
                cid = w.ins("claims", {"project_id": w.project_id, "person_id": pid, "claim_type": "name", "date_qualifier": "unknown",
                                       "value_text": p.display_name, "statement": "Person-level and name citations from the tree",
                                       "status": "working", "status_note": _status_note(w), "origin": "import", "created_at": w.ts, "updated_at": w.ts})
                w.link("claim", cid, anchor, key, p.node.all("SOUR") + [n.node for n in p.names if n.citations])
                seen_links.add((anchor, key))
            else:
                cid = _linked_entity(conn, w.lineage_id, anchor, key)
            if cid:
                _cite(conn, w, cid, idcites, cite_sources)
        _attach_media(conn, settings, w, p.media, "person", pid, root, written_files)
        current_by_anchor.setdefault(anchor, set()).update(current_keys)

    # ---- families → relationships and couple events
    for fam in m.families.values():
        partners = [x for x in (fam.husb, fam.wife) if x and x in person_ids]
        if len(partners) == 2:
            a, b_ = partners
            key = "rel:spouse:" + anchors[b_]
            if (anchors[a], key) not in seen_links:
                cid = w.ins("claims", {"project_id": w.project_id, "person_id": person_ids[a], "claim_type": "relationship",
                                       "relationship_type": "spouse", "related_person_id": person_ids[b_],
                                       "statement": f"Partners in family {fam.xref} in the tree", "status": "tentative",
                                       "status_note": _status_note(w), "origin": "import", "date_qualifier": "unknown",
                                       "created_at": w.ts, "updated_at": w.ts})
                w.link("claim", cid, anchors[a], key, {**node_json(fam.node), "children": [node_json(c) for c in fam.node.children if c.tag in ("HUSB", "WIFE")]})
                seen_links.add((anchors[a], key))
                w.bump("relationships_partner")
        for f in fam.facts:
            for i, who in enumerate(partners):
                other = partners[1 - i] if len(partners) == 2 else None
                key = f.key + ":" + (anchors[other] if other else "-")
                current_by_anchor.setdefault(anchors[who], set()).add(key)
                if (anchors[who], key) in seen_links:
                    w.bump("facts_already_imported")
                    continue
                cid = _fact_claim(conn, w, person_ids[who], f, person_ids[other] if other else None)
                w.link("claim", cid, anchors[who], key, f.node)
                seen_links.add((anchors[who], key))
                _cite(conn, w, cid, f.citations, cite_sources)
            if partners:
                _attach_media(conn, settings, w, f.media, "person", person_ids[partners[0]], root, written_files)
        if partners:
            _attach_media(conn, settings, w, fam.media, "person", person_ids[partners[0]], root, written_files)
            if fam.notes:
                w.bump("family_notes", len(fam.notes))
    for r in relationships(m):
        if r["kind"] != "child" or r["child"] not in person_ids or r["parent"] not in person_ids:
            continue
        anchor = anchors[r["child"]]
        key = f"rel:child:{anchors[r['parent']]}:{r['raw'] or ''}"
        if (anchor, key) in seen_links:
            continue
        q = r["qualifier"]
        qtxt = f"recorded as “{r['raw']}”" if r["raw"] else (
            "relationship type not stated in the file (Ancestry exports leave it out when the link is biological)"
            if w.batch["product"] == "ancestry" else "relationship type not stated in the file")
        fam = m.families[r["fam"]]
        chil_nodes = [c for c in fam.node.all("CHIL") if c.value.strip() == r["child"]]
        cid = w.ins("claims", {"project_id": w.project_id, "person_id": person_ids[r["child"]], "claim_type": "relationship",
                               "relationship_type": "child", "related_person_id": person_ids[r["parent"]], "relationship_qualifier": q,
                               "statement": f"Child of {m.people[r['parent']].display_name} ({r['role']}) in family {r['fam']}; {qtxt}",
                               "status": "tentative", "status_note": _status_note(w), "origin": "import", "date_qualifier": "unknown",
                               "created_at": w.ts, "updated_at": w.ts})
        w.link("claim", cid, anchor, key, [node_json(n) for n in chil_nodes] + [node_json(c) for c in fam.node.children if c.tag in ("HUSB", "WIFE")])
        seen_links.add((anchor, key))
        w.bump("relationships_parent_child")
        w.bump(f"relationship_{q or 'not_stated'}")
    if repeat:
        for p in m.people.values():
            _flag_removed_facts(conn, w, anchors[p.xref], person_ids[p.xref], p, current_by_anchor.get(anchors[p.xref], set()))
    report = {"stats": w.stats}
    report["media"] = rows(conn, "SELECT file_ref, owner_type, owner_xref, kind, status, matched_path, candidates_json, attachment_id, note FROM import_media WHERE batch_id = ?",
                           (w.batch["id"],))
    ms = {}
    for x in report["media"]:
        ms[x["status"]] = ms.get(x["status"], 0) + 1
    report["media_summary"] = ms
    report["review_pending"] = one(conn, "SELECT COUNT(*) AS n FROM import_review_items WHERE batch_id = ? AND status = 'pending'", (w.batch["id"],))["n"]
    report["profiles"] = w.batch["plan"].get("profiles", [])
    for prof in report["profiles"]:
        prof["person_id"] = person_ids.get(prof["xref"])
    return report


def _update_person_fields(conn, w: Writer, pid: str, rec: dict, mapped: dict) -> None:
    cur = one(conn, "SELECT * FROM persons WHERE id = ?", (pid,))
    link = one(conn, "SELECT * FROM import_links WHERE entity_type = 'person' AND entity_id = ? ORDER BY imported_at DESC LIMIT 1", (pid,))
    prev = (link["gedcom"][0].get("_mapped") if link else None) or {}
    changes = {}
    for k in ("display_name", "sex", "notes"):
        new, old_import, local = mapped.get(k), prev.get(k), cur.get(k)
        if new == old_import or new == local:
            continue
        if local == old_import:
            changes[k] = new
        else:
            review(conn, w, "conflicting_change", rec["xref"], "person", pid,
                   f"{cur['display_name']}: “{k}” changed in the export, but you edited it here. Your version was kept.",
                   {"field": k, "local": local, "previous_import": old_import, "new_import": new})
            w.bump("conflicts")
    if changes:
        w.changed("persons", cur)
        update(conn, "persons", pid, {**changes, "updated_at": w.ts})
    w.link("person", pid, rec["id"], "person", {"tag": "INDI", "value": "", "children": [], "raw": [], "_mapped": mapped})


def _fact_claim(conn, w: Writer, pid: str, f, related: str | None) -> str:
    bits = []
    if f.claim_type == "other" or f.custom:
        bits.append(f.label)
    if f.type_text and f.tag not in ("EVEN", "FACT"):
        bits.append(f"type: {f.type_text}")
    if f.age:
        bits.append(f"age {f.age}")
    if f.cause:
        bits.append(f"cause: {f.cause}")
    bits += f.notes
    if f.custom:
        bits.append(f"(custom tag {f.tag})")
    w.bump("facts_added")
    if f.notes:
        w.bump("fact_notes", len(f.notes))
    return w.ins("claims", {"project_id": w.project_id, "person_id": pid, "claim_type": f.claim_type, "date_text": f.date_text or None,
                            "date_qualifier": f.date["date_qualifier"], "year_from": f.date["year_from"], "year_to": f.date["year_to"],
                            "place_id": w.place(f.place), "related_person_id": related,
                            "value_text": f.value or (f.label if f.claim_type == "other" else None),
                            "statement": "; ".join(b for b in bits if b) or None, "status": "working",
                            "status_note": _status_note(w, "Marked preferred in the tree." if f.primary else ""), "origin": "import",
                            "created_at": w.ts, "updated_at": w.ts})


def _existing_fact_keys(conn, lineage_id) -> set:
    return {(r["record_xref"], r["fact_key"]) for r in rows(conn, """SELECT l.record_xref, l.fact_key FROM import_links l
            WHERE l.lineage_id = ? AND l.fact_key IS NOT NULL AND EXISTS (SELECT 1 FROM import_batches b WHERE b.id = l.batch_id AND b.status = 'committed')""",
                                                                 (lineage_id,))}


def _existing_cite_sources(conn, lineage_id) -> dict:
    out = {}
    for r in rows(conn, """SELECT l.fact_key, l.entity_id FROM import_links l JOIN sources s ON s.id = l.entity_id
                           WHERE l.lineage_id = ? AND l.entity_type = 'source'""", (lineage_id,)):
        out[r["fact_key"]] = r["entity_id"]
    return out


def _linked_entity(conn, lineage_id, anchor, key):
    r = one(conn, "SELECT entity_id FROM import_links WHERE lineage_id = ? AND record_xref = ? AND fact_key = ? ORDER BY imported_at LIMIT 1",
            (lineage_id, anchor, key))
    return r and r["entity_id"]


def _cite(conn, w: Writer, claim_id: str, citations: list, cache: dict) -> None:
    for c in citations:
        sid = cache.get(c.key)
        if not sid or not one(conn, "SELECT id FROM sources WHERE id = ?", (sid,)):
            master = w_master(w, c)
            title = master.get("title") or c.title
            parts = [title, c.page, master.get("repository"), c.apid and f"Ancestry record reference (_APID) {c.apid}"]
            text = "; ".join(p for p in parts if p) + "."
            vals = {"project_id": w.project_id, "title": title[:500], "creator": master.get("author") or None,
                    "repository": master.get("repository"), "collection_name": master.get("publication") or None,
                    "page_ref": c.page or None, "url": _url(c, master), "transcription": c.text or None,
                    "excerpt": master.get("text") or None, "record_format": "unknown", "informant_knowledge": "undetermined",
                    "citation_text": text, "origin": "import",
                    "provenance_note": (f"Imported from {w.label} ({w.snapshot}). Citation as recorded in the tree"
                                        + (f"; source record {c.sour_xref}" if c.sour_xref else "") + (f"; call number {master['call_number']}" if master.get("call_number") else "")
                                        + (f"; quality {c.quay} ({QUAY.get(str(c.quay), 'unknown scale')})" if c.quay else "") + ". Not independently reviewed."
                                        + ("\nNotes: " + " | ".join(c.notes + master.get("notes", [])) if (c.notes or master.get("notes")) else "")),
                    "created_at": w.ts, "updated_at": w.ts}
            vals["fingerprint"] = ev.fingerprint(vals)
            sid = w.ins("sources", vals)
            nodes = [c.node] + ([w.model_sources[c.sour_xref]["node"]] if c.sour_xref and c.sour_xref in w.model_sources else [])
            w.link("source", sid, "cite", c.key, nodes)
            cache[c.key] = sid
            w.bump("sources_created")
        if one(conn, "SELECT id FROM claim_evidence WHERE claim_id = ? AND source_id = ?", (claim_id, sid)):
            continue
        w.ins("claim_evidence", {"claim_id": claim_id, "source_id": sid, "stance": "supports", "identity_match": "uncertain",
                                       "assessment": "unassessed",
                                       "interpretation_note": f"Citation attached to this fact in the imported tree; not independently reviewed."
                                                              + (f" Tree quality rating {c.quay}: {QUAY.get(str(c.quay), '')}." if c.quay else ""),
                                       "created_at": w.ts, "updated_at": w.ts})
        w.bump("citations_linked")


def w_master(w: Writer, c) -> dict:
    return w.model_sources.get(c.sour_xref, {}) if c.sour_xref else {}


def _url(c, master) -> str | None:
    """Only links written in the file (citation _LINK / WWW, source WWW). No URLs are constructed."""
    for u in list(c.links) + [master.get("www") or ""]:
        if u and u.startswith(("http://", "https://")):
            return u[:1000]
    return None


def _attach_media(conn, settings, w: Writer, refs: list, owner_type: str, owner_id: str, root: Path, written: list) -> None:
    files = None
    for ref in refs:
        key = (ref["file"], ref["line"], owner_type, owner_id)   # one media item may be linked to several people
        if key in w.media_done:
            continue
        w.media_done.add(key)
        if files is None:
            files = [f for f in md.inventory(root / "media") if f != (md.safe_relpath(w.batch["gedcom_member"]) if w.batch["gedcom_member"] else None)]
        res = media_match(ref, files)
        status, note, aid = res["status"], res["how"], None
        if status == "matched":
            src = root / "media" / res["path"]
            try:
                a = att.save(conn, settings.attachments_dir, w.project_id, owner_type, owner_id, Path(res["path"]).name, src.read_bytes())
                aid = a["id"]
                written.append(str(settings.attachments_dir / a["stored_path"]))
                w.created("attachments", aid)
                w.link("attachment", aid, "media", "media:" + ref["file"], ref["node"])
                w.bump("media_copied")
            except ValidationError as e:
                status, note = "unsupported_type", str(e)
        elif status == "missing" and not files and ref["file"]:
            status = "not_supplied"
        mid = w.ins("import_media", {"batch_id": w.batch["id"], "record_xref": ref["obje_xref"], "owner_xref": ref["owner_xref"],
                                     "owner_type": owner_type, "file_ref": ref["file"] or (f"(no file) Ancestry media id {ref['oid']}" if ref.get("oid") else ""),
                                     "title": ref["title"], "form": ref["form"],
                                     "kind": "remote" if (md.is_remote(ref["file"]) or not ref["file"]) else "local", "status": status,
                                     "matched_path": res["path"], "candidates_json": json.dumps(res["candidates"]), "attachment_id": aid, "note": note})
        if status == "ambiguous":
            review(conn, w, "ambiguous_media", ref["owner_xref"], owner_type, owner_id,
                   f"Media reference “{ref['file']}” matches {len(res['candidates'])} supplied files. Choose one, or leave it unattached.",
                   {"media_id": mid, "candidates": res["candidates"], "file_ref": ref["file"]})


def _flag_removed_facts(conn, w: Writer, anchor: str, pid: str, p: Person, current_keys: set) -> None:
    prior = rows(conn, """SELECT l.entity_id, l.fact_key, l.entity_type FROM import_links l JOIN import_batches b ON b.id = l.batch_id
                          WHERE l.lineage_id = ? AND l.record_xref = ? AND l.entity_type IN ('claim', 'name') AND b.status = 'committed'
                          AND l.fact_key NOT LIKE 'rel:%'""", (w.lineage_id, anchor))
    for r in prior:
        if r["fact_key"] in current_keys or r["fact_key"] == "person":
            continue
        if r["entity_type"] == "claim":
            c = one(conn, "SELECT * FROM claims WHERE id = ?", (r["entity_id"],))
            if not c or c["status"] == "rejected":
                continue
            what = f"{c['claim_type']} {c['date_text'] or ''}".strip()
        else:
            c = one(conn, "SELECT * FROM person_names WHERE id = ?", (r["entity_id"],))
            if not c:
                continue
            what = f"name {c['full_text'] or ''}"
        if one(conn, "SELECT id FROM import_review_items WHERE entity_id = ? AND kind = 'removed_in_source' AND status = 'pending'", (r["entity_id"],)):
            continue
        review(conn, w, "removed_in_source", p.xref, r["entity_type"], r["entity_id"],
               f"{p.display_name}: {what} was in an earlier import but is not in this export (it may have been edited or deleted in the tree). Kept unchanged.", {})
        w.bump("facts_missing_from_export")


def review(conn, w: Writer, kind, xref, entity_type, entity_id, summary, detail) -> None:
    w.ins("import_review_items", {"batch_id": w.batch["id"], "kind": kind, "record_xref": xref, "entity_type": entity_type,
                                        "entity_id": entity_id, "summary": summary, "detail_json": json.dumps(detail, default=str),
                                        "status": "pending", "created_at": w.ts})


# ======================================================================= undo & review

UNDO_TABLES_WITH_EDITS = {"persons", "claims", "sources"}


def undo(conn, settings, batch_id: str) -> dict:
    b = get_batch_row(conn, batch_id)
    if b["status"] != "committed":
        raise ValidationError("Only a committed import can be undone.")
    later = one(conn, "SELECT id FROM import_batches WHERE lineage_id = ? AND status = 'committed' AND committed_at > ?",
                (b["lineage_id"], b["committed_at"]))
    if later:
        raise ValidationError("A later import of this tree exists. Undo the most recent import first.")
    safety = port.create_backup(settings, "pre-undo")
    kept = []
    if b["created_project"] and b["project_id"]:
        att.delete_for_project(conn, settings.attachments_dir, b["project_id"])
        with Tx(conn):
            conn.execute("DELETE FROM projects WHERE id = ?", (b["project_id"],))
            update(conn, "import_batches", batch_id, {"status": "undone", "undone_at": now_iso()})
        return {"undone": True, "project_deleted": True, "safety_backup": safety.name, "kept_because_edited": []}
    changes = rows(conn, "SELECT * FROM import_changes WHERE batch_id = ? ORDER BY id DESC", (batch_id,))
    with Tx(conn):
        for ch in changes:
            table, rid = ch["table_name"], ch["row_id"]
            cur = one(conn, f"SELECT * FROM {table} WHERE id = ?", (rid,)) if table in ALLOWED_UNDO else None
            if table not in ALLOWED_UNDO:
                continue
            if cur is None:
                continue
            if table in UNDO_TABLES_WITH_EDITS and cur.get("updated_at") and cur["updated_at"] > (b["committed_at"] or ""):
                kept.append({"table": table, "id": rid, "reason": "edited after the import"})
                continue
            if ch["before"] is None:
                if table == "attachments":
                    att.delete(conn, settings.attachments_dir, rid)
                else:
                    conn.execute(f"DELETE FROM {table} WHERE id = ?", (rid,))
            else:
                before = ch["before"]
                cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                vals = {}
                for k, v in before.items():
                    col = k if k in cols else (k + "_json" if k + "_json" in cols else None)
                    if col and col != "id":
                        vals[col] = json.dumps(v) if col.endswith("_json") and not isinstance(v, str) else v
                update(conn, table, rid, vals)
        update(conn, "import_batches", batch_id, {"status": "undone", "undone_at": now_iso()})
    return {"undone": True, "project_deleted": False, "safety_backup": safety.name, "kept_because_edited": kept}


ALLOWED_UNDO = {"persons", "person_names", "claims", "sources", "claim_evidence", "places", "attachments", "import_records", "import_links",
                "import_media", "import_review_items"}


def decide_review(conn, settings, item_id: str, accept: bool, choice: str | None = None) -> dict:
    it = one(conn, "SELECT * FROM import_review_items WHERE id = ?", (item_id,))
    if not it:
        raise NotFound("review item")
    if it["status"] != "pending":
        raise ValidationError("Already decided")
    d = it["detail"] or {}
    resolution = "kept as is"
    with Tx(conn):
        if it["kind"] == "uncertain_match":
            new_rec = one(conn, "SELECT * FROM import_records WHERE id = ?", (d["new_record_id"],))
            if accept:
                # Treat as the same person: move the newly imported facts onto the existing person (your explicit decision).
                old_pid, new_pid = d["existing_person_id"], it["entity_id"]
                if not one(conn, "SELECT id FROM persons WHERE id = ?", (old_pid,)):
                    raise ValidationError("The earlier person no longer exists.")
                for t, col in (("claims", "person_id"), ("person_names", "person_id")):
                    conn.execute(f"UPDATE {t} SET {col} = ? WHERE {col} = ?", (old_pid, new_pid))
                conn.execute("UPDATE claims SET related_person_id = ? WHERE related_person_id = ?", (old_pid, new_pid))
                conn.execute("UPDATE attachments SET owner_id = ? WHERE owner_type = 'person' AND owner_id = ?", (old_pid, new_pid))
                conn.execute("UPDATE import_links SET entity_id = ? WHERE entity_type = 'person' AND entity_id = ?", (old_pid, new_pid))
                conn.execute("DELETE FROM persons WHERE id = ?", (new_pid,))
                old_rec = one(conn, "SELECT * FROM import_records WHERE id = ?", (d["existing_record_id"],))
                conn.execute("UPDATE import_links SET record_xref = ? WHERE record_xref = ?", (old_rec["id"], new_rec["id"]))
                keys = sorted(set(old_rec["stable_keys"] or []) | set(new_rec["stable_keys"] or []))
                update(conn, "import_records", old_rec["id"], {"xref": new_rec["xref"], "stable_keys_json": json.dumps(keys),
                                                               "raw_json": json.dumps(new_rec["raw"], ensure_ascii=False),
                                                               "content_hash": new_rec["content_hash"], "updated_at": now_iso()})
                conn.execute("DELETE FROM import_records WHERE id = ?", (new_rec["id"],))
                resolution = "linked to the earlier person; facts moved onto that person"
            else:
                if new_rec:
                    keys = sorted(set(new_rec["stable_keys"] or []) | {f"distinct:{d['existing_record_id']}"})
                    update(conn, "import_records", new_rec["id"], {"stable_keys_json": json.dumps(keys)})
                resolution = "kept as separate people"
        elif it["kind"] == "conflicting_change":
            if accept:
                update(conn, "persons", it["entity_id"], {d["field"]: d["new_import"], "updated_at": now_iso()})
                resolution = "applied the exported value"
            else:
                resolution = "kept your local value"
        elif it["kind"] == "removed_in_source":
            if accept and it["entity_type"] == "claim":
                update(conn, "claims", it["entity_id"], {"status": "rejected", "status_note": "Removed from the tree in a later export (marked on review).",
                                                         "updated_at": now_iso()})
                resolution = "claim marked rejected (kept for the record)"
            else:
                resolution = "kept unchanged"
        elif it["kind"] == "ambiguous_media":
            mrow = one(conn, "SELECT * FROM import_media WHERE id = ?", (d["media_id"],))
            if accept:
                if choice not in d["candidates"]:
                    raise ValidationError("Choose one of the candidate files")
                b = get_batch_row(conn, it["batch_id"])
                src = imports_dir(settings) / b["stored_dir"] / "media" / choice
                a = att.save(conn, settings.attachments_dir, b["project_id"], it["entity_type"], it["entity_id"], Path(choice).name, src.read_bytes())
                update(conn, "import_media", mrow["id"], {"status": "matched", "matched_path": choice, "attachment_id": a["id"],
                                                          "note": "chosen during review"})
                resolution = f"attached {choice}"
            else:
                resolution = "left unattached"
        update(conn, "import_review_items", item_id, {"status": "accepted" if accept else "rejected", "resolution": resolution,
                                                      "decided_at": now_iso()})
    return one(conn, "SELECT * FROM import_review_items WHERE id = ?", (item_id,))


# ======================================================================= queries

def get_batch_row(conn, batch_id: str) -> dict:
    b = one(conn, "SELECT * FROM import_batches WHERE id = ?", (batch_id,))
    if not b:
        raise NotFound("import")
    return b


def get_batch(conn, batch_id: str) -> dict:
    b = get_batch_row(conn, batch_id)
    b["review"] = rows(conn, "SELECT * FROM import_review_items WHERE batch_id = ? ORDER BY status DESC, kind, created_at", (batch_id,))
    b["lineage"] = one(conn, "SELECT * FROM import_lineages WHERE id = ?", (b["lineage_id"],)) if b["lineage_id"] else None
    b["can_undo"] = b["status"] == "committed" and not one(conn, """SELECT id FROM import_batches WHERE lineage_id = ? AND status = 'committed'
                                                                   AND committed_at > ?""", (b["lineage_id"], b["committed_at"]))
    return b


def list_batches(conn) -> list[dict]:
    return rows(conn, """SELECT b.id, b.status, b.original_filename, b.product, b.gedcom_version, b.encoding, b.created_at, b.committed_at,
                         b.undone_at, b.project_id, b.lineage_id, p.name AS project_name, l.tree_label,
                         (SELECT COUNT(*) FROM import_review_items r WHERE r.batch_id = b.id AND r.status = 'pending') AS review_pending
                         FROM import_batches b LEFT JOIN projects p ON p.id = b.project_id LEFT JOIN import_lineages l ON l.id = b.lineage_id
                         ORDER BY b.created_at DESC""")


def lineages(conn) -> list[dict]:
    return rows(conn, """SELECT l.*, p.name AS project_name,
                         (SELECT MAX(committed_at) FROM import_batches b WHERE b.lineage_id = l.id AND b.status = 'committed') AS last_import
                         FROM import_lineages l JOIN projects p ON p.id = l.project_id ORDER BY l.created_at DESC""")


def provenance(conn, entity_type: str, entity_id: str) -> list[dict]:
    out = rows(conn, """SELECT l.*, b.original_filename, b.product, b.committed_at, b.status AS batch_status, li.tree_label
                        FROM import_links l JOIN import_batches b ON b.id = l.batch_id LEFT JOIN import_lineages li ON li.id = l.lineage_id
                        WHERE l.entity_type = ? AND l.entity_id = ? ORDER BY l.imported_at""", (entity_type, entity_id))
    return out


def person_provenance(conn, person_id: str) -> dict:
    """Side-by-side: imported values next to the original GEDCOM lines, for the person and each claim/name/source."""
    person = provenance(conn, "person", person_id)
    claims = rows(conn, "SELECT id, claim_type, date_text, statement, value_text, relationship_type, relationship_qualifier, status FROM claims WHERE person_id = ?",
                  (person_id,))
    names = rows(conn, "SELECT id, name_type, given, surname, full_text FROM person_names WHERE person_id = ?", (person_id,))
    items = []
    for c in claims:
        p = provenance(conn, "claim", c["id"])
        if p:
            items.append({"entity_type": "claim", "entity": c, "links": p})
    for n in names:
        p = provenance(conn, "name", n["id"])
        if p:
            items.append({"entity_type": "name", "entity": n, "links": p})
    rec = one(conn, """SELECT r.raw_json, r.xref, r.stable_keys_json, l.tree_label, l.product FROM import_records r JOIN import_lineages l ON l.id = r.lineage_id
                       WHERE r.entity_type = 'person' AND r.entity_id = ?""", (person_id,))
    return {"person": person, "items": items, "record": rec}


def mark_checked(conn, batch_id: str, checked: bool) -> dict:
    b = get_batch_row(conn, batch_id)
    rep = b["report"] or {}
    rep["checked_at"] = now_iso() if checked else None
    update(conn, "import_batches", batch_id, {"report_json": json.dumps(rep, ensure_ascii=False, default=str)})
    return get_batch(conn, batch_id)


def discard(conn, settings, batch_id: str) -> None:
    b = get_batch_row(conn, batch_id)
    if b["status"] != "previewed":
        raise ValidationError("Only an import that has not been committed can be discarded.")
    shutil.rmtree(imports_dir(settings) / b["stored_dir"], ignore_errors=True)
    update(conn, "import_batches", batch_id, {"status": "discarded"})


def one_or_404(conn, sql, rid, label):
    r = one(conn, sql, (rid,))
    if not r:
        raise NotFound(label)
    return r


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
