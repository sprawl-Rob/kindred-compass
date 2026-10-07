"""Imported documents: certificates, letters, photos of records, scans — images or PDFs.

1. add(): store the file (as an attachment owned by the document) and queue text recognition.
2. process(): recognise the text on this Mac (app/ocr.py), make page previews, and run discovery.
3. discover(): work out what the document is (birth / marriage / death certificate, letter, …), read its
   labelled fields (child, father, mother, groom, bride, deceased, dates, places, informant…), and find
   which people in the tree it names.
4. attach(): turn it into a source (the image stays attached to it, the corrected text becomes its
   transcription) for the person it's about, add the facts and relatives you tick (reusing app/capture.py),
   and note it on anyone else it mentions.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from . import attachments as att, capture, evidence as ev, family as fam, nameequiv, placenorm, workspace as ws
from .db import Tx, connect, insert, new_id, now_iso, one, rows, update
from .directory import NotFound, ValidationError

DOC_TYPES = {"birth": "Birth certificate / record", "baptism": "Baptism record", "marriage": "Marriage certificate / record",
             "death": "Death certificate / record", "burial": "Burial / cemetery record", "obituary": "Obituary / newspaper clipping",
             "letter": "Letter", "naturalization": "Naturalization papers", "immigration": "Passenger / immigration record",
             "military": "Military record", "census": "Census page", "photo": "Photograph", "other": "Other document"}
TYPE_RULES = [
    ("naturalization", r"naturali[sz]ation|declaration of intention|petition for citizenship|certificate of citizenship|oath of allegiance"),
    ("marriage", r"certificate of marriage|marriage certificate|record of marriage|marriage license|license to marry|bride|groom|intentions? of marriage|were united in marriage"),
    ("death", r"certificate of death|death certificate|record of death|cause of death|date of death|deceased|standard certificate of death"),
    ("birth", r"certificate of birth|birth certificate|record of birth|certificate of live birth|name of child|date of birth"),
    ("baptism", r"baptism|baptismal|christening|was baptized|baptisé|baptisée|döpt|getauft"),
    ("burial", r"interment|burial permit|cemetery|grave|lot no"),
    ("obituary", r"obituary|funeral (will be|services)|passed away|survived by|died (at|yesterday|on)"),
    ("immigration", r"passenger|manifest|steamship|port of arrival|alien passengers"),
    ("military", r"draft|registration card|enlist|discharge|regiment|service record|selective service"),
    ("census", r"census|enumerat"),
    ("letter", r"^\s*dear\b|\byours (truly|sincerely|affectionately)|\bsincerely\b|\byour (loving|affectionate)\b"),
]
MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE_RE = re.compile(rf"\b(?:{MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+1[5-9]\d\d|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{MONTHS}\.?,?\s+1[5-9]\d\d|\d{{1,2}}/\d{{1,2}}/1[5-9]\d\d|{MONTHS}\.?\s+1[5-9]\d\d)\b", re.I)

_lock = threading.Lock()


# ------------------------------------------------------------------ storing and processing

def add(conn, settings, project_id: str, filename: str, data: bytes, person_id: str | None = None) -> dict:
    ws.get_project(conn, project_id)
    did, ts = new_id(), now_iso()
    with Tx(conn):
        insert(conn, "documents", {"id": did, "project_id": project_id, "title": Path(filename).stem[:200], "status": "processing",
                                   "original_name": att.safe_name(filename), "person_ids_json": json.dumps([person_id] if person_id else []),
                                   "created_at": ts, "updated_at": ts})
        a = att.save(conn, settings.attachments_dir, project_id, "document", did, filename, data)
        update(conn, "documents", did, {"attachment_id": a["id"]})
    return get(conn, did)


def process(settings, doc_id: str) -> None:
    """Recognise text and make previews (runs in a background thread)."""
    from . import ocr
    conn = connect(settings.db_path)
    try:
        d = one(conn, "SELECT * FROM documents WHERE id = ?", (doc_id,))
        if not d:
            return
        a = att.get(conn, d["attachment_id"])
        path = att.path_for(settings.attachments_dir, a)
        try:
            _previews(settings, d, path)
        except Exception:  # noqa: BLE001 - previews are a convenience
            pass
        try:
            with _lock:    # Vision is heavy; one document at a time
                r = ocr.ocr_file(path)
            text = r["text"] or ""
            det = discover(conn, d["project_id"], text, d["original_name"])
            update(conn, "documents", doc_id, {"ocr_text": text, "ocr_engine": r["engine"], "ocr_confidence": r["confidence"], "pages": r["pages"],
                                               "doc_type": det["doc_type"], "title": det["title"] or d["title"], "detected_json": json.dumps(det),
                                               "status": "ready" if d["status"] != "attached" else "attached", "error": None, "updated_at": now_iso()})
        except Exception as e:  # noqa: BLE001
            update(conn, "documents", doc_id, {"status": "failed" if d["status"] != "attached" else "attached",
                                               "error": f"{type(e).__name__}: {e}"[:400], "updated_at": now_iso()})
    finally:
        conn.close()


def start_processing(settings, doc_id: str) -> None:
    threading.Thread(target=process, args=(settings, doc_id), daemon=True).start()


def preview_dir(settings, project_id: str) -> Path:
    return Path(settings.attachments_dir) / project_id / "previews"


def _previews(settings, d: dict, path: Path, max_pages: int = 30) -> int:
    """JPEG previews (so HEIC, TIFF and PDF pages can be viewed in the browser)."""
    import Quartz
    from Foundation import NSURL
    out = preview_dir(settings, d["project_id"])
    out.mkdir(parents=True, exist_ok=True)
    n = 0

    def write(img, k):
        dest = Quartz.CGImageDestinationCreateWithURL(NSURL.fileURLWithPath_(str(out / f"{d['id']}-{k}.jpg")), "public.jpeg", 1, None)
        Quartz.CGImageDestinationAddImage(dest, img, {Quartz.kCGImageDestinationLossyCompressionQuality: 0.82})
        Quartz.CGImageDestinationFinalize(dest)
    if path.suffix.lower() == ".pdf":
        from .ocr import _render
        doc = Quartz.CGPDFDocumentCreateWithURL(NSURL.fileURLWithPath_(str(path)))
        for i in range(min(Quartz.CGPDFDocumentGetNumberOfPages(doc), max_pages)):
            page = Quartz.CGPDFDocumentGetPage(doc, i + 1)
            box = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
            img = _render(page, scale=min(2.0, 1600 / max(1, box.size.width)))
            if img is not None:
                n += 1
                write(img, n)
    else:
        src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(path)), None)
        if src is None:
            return 0
        opts = {Quartz.kCGImageSourceCreateThumbnailFromImageAlways: True, Quartz.kCGImageSourceThumbnailMaxPixelSize: 2000,
                Quartz.kCGImageSourceCreateThumbnailWithTransform: True}
        img = Quartz.CGImageSourceCreateThumbnailAtIndex(src, 0, opts)
        if img is not None:
            n = 1
            write(img, 1)
    return n


def preview_path(settings, d: dict, page: int) -> Path:
    return preview_dir(settings, d["project_id"]) / f"{d['id']}-{page}.jpg"


# ------------------------------------------------------------------ discovery

def discover(conn, project_id: str, text: str, filename: str = "") -> dict:
    low = (text or "").lower()
    doc_type = "other"
    for t, pat in TYPE_RULES:
        if re.search(pat, low, re.M):
            doc_type = t
            break
    if doc_type == "other" and not text.strip():
        doc_type = "photo"
    parsed = capture.parse(text, None, DOC_TYPES[doc_type]) if text.strip() else {"fields": {}, "household": []}
    F = parsed.get("fields") or {}
    dates = list(dict.fromkeys(m.group(0) for m in DATE_RE.finditer(text or "")))[:12]
    years = sorted({int(y) for y in re.findall(r"\b(1[6-9]\d\d|20[0-2]\d)\b", text or "")})
    # people in the tree named in the document
    f = fam.load(conn, project_id)
    folded = nameequiv.fold(text or "")
    mentioned = []
    for k, p in f.people.items():
        given = (nameequiv.strip_quoted(p.givens[0]).split() or [""])[0] if p.givens else ""
        if not given:
            continue
        surnames = [s for s in (p.surnames + p.married_surnames + [f.search_surname(k)]) if s]
        forms = {nameequiv.fold(given)} | {nameequiv.fold(x) for x in nameequiv.given_equivalents(given) if len(x) > 2}
        hits = 0
        for sn in dict.fromkeys(nameequiv.fold(s) for s in surnames):
            for g in forms:
                hits += len(re.findall(rf"\b{re.escape(g)}(?: [a-z]\b| [a-z]{{2,12}})? {re.escape(sn)}\b|\b{re.escape(sn)},? {re.escape(g)}\b", folded))
        if hits:
            mentioned.append({**f.summary(k), "count": hits})
    mentioned.sort(key=lambda m: -m["count"])
    subject_name = F.get("name") or F.get("groom") or F.get("bride")
    subjects = []
    for m in mentioned:
        if subject_name and _same(subject_name, m["name"]):
            subjects.append(m["id"])
    places = []
    for k, p in f.people.items():
        for e in p.events:
            t = e.place.town
            if t and len(t) > 3 and re.search(rf"\b{re.escape(nameequiv.fold(t))}\b", folded) and t.lower() not in {x.lower() for x in places}:
                places.append(t)
    title = _title(doc_type, F, years)
    return {"doc_type": doc_type, "doc_type_label": DOC_TYPES[doc_type], "fields": F, "household": parsed.get("household") or [],
            "dates": dates, "years": years[:20], "places": places[:10], "mentioned": mentioned[:20], "subjects": subjects, "title": title}


def _same(a: str, b: str) -> bool:
    fa, fb = nameequiv.fold(a).split(), nameequiv.fold(b.replace('"', "")).split()
    if not fa or not fb:
        return False
    return fa[-1] == fb[-1] and (fa[0] == fb[0] or fb[0] in {nameequiv.fold(x) for x in nameequiv.given_equivalents(fa[0])})


def _title(doc_type, F, years) -> str | None:
    who = F.get("name") or (" & ".join(x for x in [F.get("groom"), F.get("bride")] if x)) or None
    when = None
    for k in ("birth_date", "marriage_date", "death_date", "event_date"):
        y = re.findall(r"\b(1[6-9]\d\d|20[0-2]\d)\b", F.get(k) or "")
        if y:
            when = y[0]
            break
    label = {"birth": "Birth certificate", "marriage": "Marriage certificate", "death": "Death certificate", "baptism": "Baptism record",
             "burial": "Burial record", "obituary": "Obituary", "letter": "Letter", "naturalization": "Naturalization papers",
             "immigration": "Passenger record", "military": "Military record", "census": "Census page"}.get(doc_type)
    if not label and not who:
        return None
    return " — ".join(x for x in [label or "Document", who, when] if x)


# ------------------------------------------------------------------ reading back and attaching

def get(conn, doc_id: str) -> dict:
    d = one(conn, "SELECT * FROM documents WHERE id = ?", (doc_id,))
    if not d:
        raise NotFound("document")
    d["text"] = d["transcription"] if d["transcription"] is not None else (d["ocr_text"] or "")
    d["person_ids"] = d.pop("person_ids", None) or []
    d["detected"] = d.get("detected") or {}
    d["type_label"] = DOC_TYPES.get(d["doc_type"] or "other", "Document")
    d["ai"] = d.pop("ai", None) or None
    d["sensitivity"] = sensitivity_warnings(d)
    if d["person_ids"]:
        d["people"] = rows(conn, f"SELECT id, display_name FROM persons WHERE id IN ({','.join('?' * len(d['person_ids']))})", tuple(d["person_ids"]))
    else:
        d["people"] = []
    return d


def list_docs(conn, project_id: str, status: str | None = None, person_id: str | None = None) -> list:
    q = "SELECT * FROM documents WHERE project_id = ?"
    args: list = [project_id]
    if status == "inbox":
        q += " AND status != 'attached'"
    if person_id:
        q += " AND person_ids_json LIKE ?"
        args.append(f'%"{person_id}"%')
    out = []
    for d in rows(conn, q + " ORDER BY created_at DESC", tuple(args)):
        d["person_ids"] = d.pop("person_ids", None) or []
        det = d.pop("detected", None) or {}
        d["detected_summary"] = {"subjects": det.get("subjects", []), "mentioned": [m["name"] for m in det.get("mentioned", [])][:5],
                                 "years": det.get("years", [])[:6]}
        d.pop("ocr_text", None)
        d.pop("transcription", None)
        d["has_ai"] = bool(d.pop("ai", None))
        d["type_label"] = DOC_TYPES.get(d["doc_type"] or "other", "Document")
        out.append(d)
    return out


def update_doc(conn, doc_id: str, data: dict) -> dict:
    d = get(conn, doc_id)
    patch = {"updated_at": now_iso()}
    if "title" in data:
        patch["title"] = (data["title"] or "")[:300]
    if "doc_type" in data:
        if data["doc_type"] not in DOC_TYPES:
            raise ValidationError("Unknown document type")
        patch["doc_type"] = data["doc_type"]
    if "transcription" in data:
        patch["transcription"] = data["transcription"]
        det = discover(conn, d["project_id"], data["transcription"] or "", d["original_name"])
        if "doc_type" not in data:
            patch["doc_type"] = det["doc_type"]
        patch["detected_json"] = json.dumps(det)
    update(conn, "documents", doc_id, patch)
    if d["source_id"] and "transcription" in data:
        update(conn, "sources", d["source_id"], {"transcription": data["transcription"], "updated_at": now_iso()})
    return get(conn, doc_id)


def parsed_for(conn, d: dict, person_id: str) -> dict:
    """The document's fields arranged around the chosen person (e.g. on a marriage record, the other party is the spouse)."""
    det = d["detected"]
    F = dict(det.get("fields") or {})
    p = one(conn, "SELECT display_name FROM persons WHERE id = ?", (person_id,))
    if F.get("groom") and F.get("bride"):
        if _same(F["bride"], p["display_name"]):
            F["name"], F["spouse"] = F["bride"], F["groom"]
        else:
            F["name"], F["spouse"] = F["groom"], F["bride"]
    year = None
    for k in ("birth_date", "marriage_date", "death_date", "event_date"):
        y = re.findall(r"\b(1[6-9]\d\d|20[0-2]\d)\b", F.get(k) or "")
        if y:
            year = int(y[0])
            break
    kind = d["doc_type"] or "other"
    return {"fields": F, "household": det.get("household") or [], "collection": d["title"] or DOC_TYPES.get(kind),
            "kind": {"birth": "birth", "baptism": "baptism", "marriage": "marriage", "death": "death", "burial": "burial",
                     "obituary": "obituary", "census": "census"}.get(kind, "other"),
            "year": year, "site": None, "url": None, "title": d["title"]}


def preview_attach(conn, doc_id: str, person_id: str) -> dict:
    d = get(conn, doc_id)
    pv = capture.preview(conn, person_id, parsed_for(conn, d, person_id))
    pv["source"] = {"title": d["title"] or d["original_name"], "repository": "Family papers", "record_date_text": pv["source"].get("record_date_text"),
                    "url": None, "record_format": "original_image",
                    "citation": f"{d['title'] or d['original_name']}; digital image of the document in the researcher's possession (file “{d['original_name']}”)."}
    pv["also_mentioned"] = [m for m in d["detected"].get("mentioned", []) if m["id"] != person_id]
    return pv


def attach(conn, settings, doc_id: str, body: dict) -> dict:
    d = get(conn, doc_id)
    person_id = body.get("person_id")
    if not person_id or not one(conn, "SELECT id FROM persons WHERE id = ? AND project_id = ?", (person_id, d["project_id"])):
        raise ValidationError("Choose who the document is about")
    src = body.get("source") or {}
    with Tx(conn):
        if d["source_id"] and one(conn, "SELECT id FROM sources WHERE id = ?", (d["source_id"],)):
            sid = d["source_id"]
        else:
            s = ev.create_source(conn, d["project_id"], {"title": (src.get("title") or d["title"] or d["original_name"])[:500],
                                                          "repository": src.get("repository") or "Family papers",
                                                          "record_date_text": src.get("record_date_text"), "citation_text": src.get("citation"),
                                                          "transcription": d["text"] or None, "record_format": src.get("record_format") or "original_image",
                                                          "provenance_note": f"Imported document “{d['original_name']}”; text recognised with {d['ocr_engine'] or 'no OCR'}"
                                                                             + (" and corrected by the user" if d["transcription"] is not None else "") + ".",
                                                          "allow_duplicate": True})
            sid = s["id"]
            # the file now belongs to the source as well (copy the attachment row; same file)
            if d["attachment_id"]:
                a = att.get(conn, d["attachment_id"])
                insert(conn, "attachments", {**{k: a[k] for k in ("original_name", "stored_path", "mime_type", "size_bytes", "sha256")},
                                             "id": new_id(), "project_id": d["project_id"], "owner_type": "source", "owner_id": sid, "created_at": now_iso()})
        result = capture.save(conn, person_id, {"source_id": sid, "facts": body.get("facts") or [], "people": body.get("people") or [],
                                                "source": src})
        people = list(dict.fromkeys([person_id] + list(d["person_ids"]) + list(body.get("also") or [])))
        for other in body.get("also") or []:
            if one(conn, "SELECT id FROM persons WHERE id = ? AND project_id = ?", (other, d["project_id"])):
                _mention(conn, d["project_id"], other, sid)
        update(conn, "documents", doc_id, {"status": "attached", "source_id": sid, "person_ids_json": json.dumps(people), "updated_at": now_iso()})
    return {**get(conn, doc_id), "saved": result}


def _mention(conn, project_id, person_id, source_id):
    c = one(conn, "SELECT id FROM claims WHERE person_id = ? AND claim_type = 'other' AND value_text = 'Documents that mention this person'", (person_id,))
    cid = c["id"] if c else ws.create_claim(conn, project_id, {"person_id": person_id, "claim_type": "other", "value_text": "Documents that mention this person",
                                                                "status": "working", "statement": "Holder for documents and records that name this person."})["id"]
    if not one(conn, "SELECT id FROM claim_evidence WHERE claim_id = ? AND source_id = ?", (cid, source_id)):
        ev.link_evidence(conn, cid, source_id, {"stance": "mentions", "identity_match": "probable", "assessment": "unassessed"})


def delete(conn, settings, doc_id: str) -> None:
    d = get(conn, doc_id)
    if d["attachment_id"]:
        shared = one(conn, "SELECT COUNT(*) AS n FROM attachments WHERE stored_path = (SELECT stored_path FROM attachments WHERE id = ?)", (d["attachment_id"],))
        if shared and shared["n"] > 1:
            conn.execute("DELETE FROM attachments WHERE id = ?", (d["attachment_id"],))   # the file stays with its source
        else:
            att.delete(conn, settings.attachments_dir, d["attachment_id"])
    for p in preview_dir(settings, d["project_id"]).glob(f"{doc_id}-*.jpg"):
        p.unlink(missing_ok=True)
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


# ------------------------------------------------------------------ AI-assisted reading

SSN_RE = re.compile(r"\b(?!000|666|9\d\d)\d{3}[- ]?(?!00)\d{2}[- ]?(?!0000)\d{4}\b")


def mask_numbers(text: str) -> str:
    """Belt and braces: hide anything shaped like a Social Security number."""
    return SSN_RE.sub("[number withheld]", text or "")


def sensitivity_warnings(d: dict) -> list:
    text = ((d.get("ocr_text") or "") + " " + (d.get("title") or "") + " " + (d.get("original_name") or "")).lower()
    out = []
    if re.search(r"social security|ssn|dd[ -]?214|service number|report of separation|military discharge", text) or SSN_RE.search(text):
        out.append("This looks like it may contain a Social Security or service number (e.g. a DD-214). The image itself is sent to the provider, "
                   "so the number will be in what they receive. The AI is told not to write such numbers out, and the app masks any that appear "
                   "in the reading — but to keep it from being sent at all, cover it (e.g. with Markup in Preview) and import the covered copy.")
    years = [int(y) for y in re.findall(r"\b(19[2-9]\d|20[0-2]\d)\b", text)]
    if years and max(years) >= 1940:
        out.append("The document has dates after 1940, so it may be about living people. Only send it if you're comfortable sharing it with the provider.")
    return out


def save_ai_reading(conn, doc_id: str, run_id: str, parsed: dict) -> None:
    clean = {"transcription": mask_numbers(parsed.get("transcription") or ""), "doc_type": parsed.get("doc_type") or "other",
             "title": mask_numbers(parsed.get("title") or ""), "fields": [{"label": f.get("label", ""), "value": mask_numbers(f.get("value", ""))}
                                                                       for f in parsed.get("fields") or [] if f.get("value")],
             "people": [{k: mask_numbers(v) for k, v in pr.items()} for pr in parsed.get("people") or []],
             "uncertainties": [mask_numbers(u) for u in parsed.get("uncertainties") or []], "run_id": run_id, "at": now_iso()}
    update(conn, "documents", doc_id, {"ai_json": json.dumps(clean, ensure_ascii=False), "ai_run_id": run_id, "updated_at": now_iso()})


def apply_ai(conn, doc_id: str) -> dict:
    """Use the AI reading: its transcription replaces the text, its fields take priority in discovery."""
    d = get(conn, doc_id)
    ai = d.get("ai") or {}
    if not ai.get("transcription"):
        raise ValidationError("There's no AI reading to use yet")
    text = ai["transcription"]
    det = discover(conn, d["project_id"], text + "\n" + "\n".join(f"{f['label']}: {f['value']}" for f in ai.get("fields") or []), d["original_name"])
    extra = {}
    for f in ai.get("fields") or []:
        k = capture._key(f["label"])
        if k and k not in ("_household",):
            extra[k] = f["value"]
    det["fields"] = {**det["fields"], **extra}
    if ai.get("doc_type") and ai["doc_type"] in DOC_TYPES:
        det["doc_type"], det["doc_type_label"] = ai["doc_type"], DOC_TYPES[ai["doc_type"]]
    det["title"] = ai.get("title") or det["title"]
    update(conn, "documents", doc_id, {"transcription": text, "doc_type": det["doc_type"], "title": det["title"] or d["title"],
                                       "detected_json": json.dumps(det), "updated_at": now_iso()})
    if d["source_id"]:
        update(conn, "sources", d["source_id"], {"transcription": text, "updated_at": now_iso()})
    return get(conn, doc_id)
