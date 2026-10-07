"""Text recognition for document images and PDFs, on this computer.

Uses Apple's Vision framework (the same text recognition as Photos and Preview), so documents never leave
the Mac. Printed text and much handwriting are recognised; old handwriting is hit and miss, so the
transcription is always editable. PDFs that already contain text use it directly; scanned PDF pages are
rendered and recognised.

On systems without Vision the functions raise OCRUnavailable and the document is kept without text.
"""
from __future__ import annotations

from pathlib import Path

LANGS = ["en-US", "fr-FR", "de-DE", "sv-SE", "es-ES", "it-IT"]   # English plus the languages of the family's records


class OCRUnavailable(Exception):
    pass


def available() -> bool:
    try:
        import Vision  # noqa: F401
        import Quartz  # noqa: F401
        return True
    except ImportError:
        return False


def _recognize(handler) -> tuple[str, float]:
    import Vision
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(True)
    try:
        req.setRecognitionLanguages_(LANGS)
    except Exception:  # noqa: BLE001
        pass
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise OCRUnavailable(f"Text recognition failed: {err}")
    obs = req.results() or []
    items = []
    for o in obs:
        cands = o.topCandidates_(1)
        if not cands:
            continue
        c = cands[0]
        box = o.boundingBox()   # normalised, origin bottom-left
        items.append((box.origin.y + box.size.height / 2, box.origin.x, box.size.height, str(c.string()), float(c.confidence())))
    if not items:
        return "", 0.0
    # group into lines (top to bottom), words left to right
    items.sort(key=lambda t: (-t[0], t[1]))
    lines, cur, cur_y, cur_h = [], [], None, None
    for y, x, h, s, conf in items:
        if cur and abs(y - cur_y) > max(cur_h, h) * 0.6:
            lines.append(cur)
            cur = []
        if not cur:
            cur_y, cur_h = y, h
        cur.append((x, s))
    if cur:
        lines.append(cur)
    text = "\n".join("\t".join(s for _, s in sorted(line)) for line in lines)
    return text, sum(t[4] for t in items) / len(items)


def ocr_image(path: Path) -> dict:
    if not available():
        raise OCRUnavailable("Text recognition needs macOS with the Vision framework")
    import Vision
    from Foundation import NSURL
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(path)), None)
    text, conf = _recognize(handler)
    return {"text": text, "confidence": round(conf, 3), "pages": 1, "engine": "Apple Vision (on this Mac)"}


def ocr_pdf(path: Path, max_pages: int = 40) -> dict:
    """Use the PDF's own text where a page has it; recognise scanned pages."""
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    n = min(len(reader.pages), max_pages)
    texts, confs, engines = [], [], set()
    doc = None
    for i in range(n):
        own = ""
        try:
            own = (reader.pages[i].extract_text() or "").strip()
        except Exception:  # noqa: BLE001
            own = ""
        if len(own) > 40:
            texts.append(own)
            engines.add("text in the PDF")
            continue
        if not available():
            texts.append("")
            continue
        import Quartz
        import Vision
        if doc is None:
            from Foundation import NSURL
            doc = Quartz.CGPDFDocumentCreateWithURL(NSURL.fileURLWithPath_(str(path)))
        page = Quartz.CGPDFDocumentGetPage(doc, i + 1)
        img = _render(page)
        if img is None:
            texts.append("")
            continue
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
        t, c = _recognize(handler)
        texts.append(t)
        confs.append(c)
        engines.add("Apple Vision (on this Mac)")
    sep = "\n\n— page {} —\n\n"
    text = texts[0] if len(texts) == 1 else "".join((sep.format(i + 1) if i else "") + t for i, t in enumerate(texts))
    return {"text": text, "confidence": round(sum(confs) / len(confs), 3) if confs else (1.0 if texts else 0.0), "pages": n,
            "engine": " + ".join(sorted(engines)) or "none", "truncated": len(reader.pages) > max_pages}


def _render(page, scale: float = 2.5):
    import Quartz
    box = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
    w, h = int(box.size.width * scale), int(box.size.height * scale)
    if w <= 0 or h <= 0 or w * h > 80_000_000:
        scale = min(scale, (80_000_000 / max(1, box.size.width * box.size.height)) ** 0.5)
        w, h = int(box.size.width * scale), int(box.size.height * scale)
    cs = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(None, w, h, 8, 0, cs, Quartz.kCGImageAlphaPremultipliedLast)
    if ctx is None:
        return None
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, w, h))
    Quartz.CGContextScaleCTM(ctx, scale, scale)
    Quartz.CGContextDrawPDFPage(ctx, page)
    return Quartz.CGBitmapContextCreateImage(ctx)


def ocr_file(path: Path) -> dict:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return ocr_pdf(path)
    if ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".bmp", ".gif", ".webp"):
        return ocr_image(path)
    if ext in (".txt", ".md"):
        return {"text": path.read_text(errors="replace"), "confidence": 1.0, "pages": 1, "engine": "text file"}
    raise OCRUnavailable(f"No text recognition for {ext} files")
