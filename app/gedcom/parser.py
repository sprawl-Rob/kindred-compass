"""GEDCOM 5.5 / 5.5.1 / 7.0 reader that preserves every line.

* Encoding is detected from the byte-order mark, then the header's CHAR value
  (UTF-8, UNICODE, ANSEL, ASCII, ANSI/Windows, IBMPC, MACINTOSH). ANSEL uses the
  `ansel` codec package. Mislabelled files are detected and reported.
* Each node keeps its level, xref, tag, value (CONT/CONC merged) and the original
  line numbers and text, so nothing is lost and the original can be shown side by side.
* Lines that cannot be parsed are reported as parsing failures (with line numbers),
  never silently dropped.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

try:
    import ansel as _ansel
    _ansel.register()
    HAVE_ANSEL = True
except Exception:  # pragma: no cover
    HAVE_ANSEL = False

LINE_RE = re.compile(r"^\s*(\d{1,3})\s+(?:(@[^@\s][^@]*@)\s+)?([A-Za-z0-9_]+)(?:[ \t](.*))?$")
CHAR_RE = re.compile(rb"^\s*1\s+CHAR\s+([A-Za-z0-9\-_ ]+?)\s*$", re.MULTILINE)
VERS_RE = re.compile(rb"^\s*2\s+VERS\s+(\S+)\s*$", re.MULTILINE)

CHARSETS = {
    "UTF-8": "utf-8", "UTF8": "utf-8", "UNICODE": "utf-16", "UTF-16": "utf-16",
    "ANSEL": "ansel", "ASCII": "ascii", "ANSI": "cp1252", "WINDOWS": "cp1252", "IBM WINDOWS": "cp1252",
    "CP1252": "cp1252", "WINDOWS-1252": "cp1252", "LATIN1": "latin-1", "ISO-8859-1": "latin-1",
    "IBMPC": "cp437", "IBM DOS": "cp437", "MACINTOSH": "mac_roman", "MACROMAN": "mac_roman",
}


@dataclass
class Node:
    level: int
    tag: str
    value: str = ""
    xref: str | None = None
    line: int = 0
    raw: list = field(default_factory=list)       # [(line_no, original text)] incl. CONT/CONC
    children: list = field(default_factory=list)

    def first(self, tag: str) -> "Node | None":
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def all(self, tag: str) -> list["Node"]:
        return [c for c in self.children if c.tag == tag]

    def val(self, tag: str, default: str | None = None) -> str | None:
        n = self.first(tag)
        return n.value if n is not None and n.value != "" else default

    def path_val(self, *tags: str) -> str | None:
        n = self
        for t in tags:
            n = n.first(t) if n else None
        return n.value if n is not None and n.value != "" else None

    def to_dict(self) -> dict:
        return {"level": self.level, "xref": self.xref, "tag": self.tag, "value": self.value, "line": self.line,
                "raw": self.raw, "children": [c.to_dict() for c in self.children]}

    def lines(self) -> list:
        out = list(self.raw)
        for c in self.children:
            out += c.lines()
        return out


@dataclass
class GedcomFile:
    head: Node | None
    records: list[Node]
    encoding: str
    declared_charset: str | None
    version: str | None
    line_count: int
    failures: list[dict]
    warnings: list[str]
    trailer_seen: bool

    def by_xref(self) -> dict[str, Node]:
        return {r.xref: r for r in self.records if r.xref}


def detect_encoding(data: bytes) -> tuple[str, str | None, list[str]]:
    """Return (python codec, declared CHAR, warnings)."""
    warnings: list[str] = []
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", _declared(data[3:]), warnings
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return "utf-16", "UNICODE", warnings
    if data[:4] in (b"0\x00 \x00", b"\x000\x00 "):
        warnings.append("File is UTF-16 without a byte-order mark.")
        return ("utf-16-le" if data[:1] == b"0" else "utf-16-be"), "UNICODE", warnings
    declared = _declared(data)
    version = _version(data)
    if version and version.startswith("7"):
        codec = "utf-8"
        if declared and declared.upper() not in ("UTF-8", "UTF8"):
            warnings.append(f"GEDCOM 7 files must be UTF-8 but the header says {declared}; reading as UTF-8.")
        return codec, declared, warnings
    codec = CHARSETS.get((declared or "").upper())
    if declared and not codec:
        warnings.append(f"Unrecognised character set “{declared}”; trying UTF-8.")
    if not declared:
        warnings.append("The header does not declare a character set; detected from content.")
    codec = codec or "utf-8"
    if codec == "ansel" and not HAVE_ANSEL:
        warnings.append("ANSEL decoding is unavailable; reading as Latin-1 (accented characters may be wrong).")
        codec = "latin-1"
    # Mislabelled files: declared single-byte but actually valid UTF-8 with non-ASCII content.
    if codec in ("ansel", "ascii", "cp1252", "latin-1", "cp437", "mac_roman") and _is_utf8_with_multibyte(data):
        warnings.append(f"Header declares {declared} but the content is valid UTF-8; reading as UTF-8.")
        codec = "utf-8"
    if codec == "utf-16" and not (data[:2] in (b"\xff\xfe", b"\xfe\xff")) and data[:1] != b"\x00" and data[1:2] != b"\x00":
        warnings.append("Header declares UNICODE but the file is not UTF-16; reading as UTF-8.")
        codec = "utf-8"
    return codec, declared, warnings


def _declared(data: bytes) -> str | None:
    head = data[:20000]
    m = CHAR_RE.search(head)
    return m.group(1).decode("ascii", "replace").strip() if m else None


def _version(data: bytes) -> str | None:
    m = VERS_RE.search(data[:20000])
    return m.group(1).decode("ascii", "replace") if m else None


def _is_utf8_with_multibyte(data: bytes) -> bool:
    if all(b < 0x80 for b in data[:200000]):
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def decode(data: bytes) -> tuple[str, str, str | None, list[str]]:
    codec, declared, warnings = detect_encoding(data)
    try:
        text = data.decode(codec)
    except (UnicodeDecodeError, LookupError):
        fallback = "utf-8" if codec != "utf-8" else "cp1252"
        try:
            text = data.decode(fallback)
            warnings.append(f"Could not decode as {codec}; decoded as {fallback} instead.")
            codec = fallback
        except UnicodeDecodeError:
            text = data.decode(codec if codec != "ansel" else "utf-8", errors="replace")
            bad = text.count("�")
            warnings.append(f"{bad} character(s) could not be decoded and were replaced with “�”. The original file is preserved unchanged.")
    # ANSEL and some Mac exports produce decomposed accents; normalise to composed form (NFC) for display and search.
    # The uploaded file itself is kept unchanged.
    return unicodedata.normalize("NFC", text.lstrip("\ufeff")), codec, declared, warnings


def parse_bytes(data: bytes) -> GedcomFile:
    text, codec, declared, warnings = decode(data)
    return parse_text(text, codec, declared, warnings)


def parse_text(text: str, codec: str = "utf-8", declared: str | None = None, warnings: list[str] | None = None) -> GedcomFile:
    warnings = list(warnings or [])
    failures: list[dict] = []
    records: list[Node] = []
    head = None
    stack: list[Node] = []
    trailer = False
    lines = text.splitlines()
    for i, rawline in enumerate(lines, start=1):
        line = rawline.rstrip("\r\n")
        if not line.strip():
            continue
        m = LINE_RE.match(line)
        if not m:
            # Some exporters wrap long values without CONT/CONC. Keep the text as a continuation, and report it.
            if stack:
                stack[-1].value += "\n" + line
                stack[-1].raw.append((i, line))
                failures.append({"line": i, "text": line[:200], "reason": "Line has no level number; kept as a continuation of the line above"})
            else:
                failures.append({"line": i, "text": line[:200], "reason": "Unparseable line before any record; skipped"})
            continue
        level, xref, tag, value = int(m.group(1)), m.group(2), m.group(3).upper(), m.group(4) or ""
        if tag in ("CONT", "CONC") and stack and level == stack[-1].level + 1:
            target = stack[-1]
            target.value += ("\n" + value) if tag == "CONT" else value
            target.raw.append((i, line))
            continue
        node = Node(level=level, tag=tag, value=value, xref=xref, line=i, raw=[(i, line)])
        if level == 0:
            stack = [node]
            if tag == "HEAD":
                head = node
            elif tag == "TRLR":
                trailer = True
            else:
                records.append(node)
            continue
        while stack and stack[-1].level >= level:
            stack.pop()
        if not stack:
            failures.append({"line": i, "text": line[:200], "reason": "Line is not inside any record; skipped"})
            continue
        if level > stack[-1].level + 1:
            failures.append({"line": i, "text": line[:200],
                             "reason": f"Level jumps from {stack[-1].level} to {level}; attached to the nearest parent"})
        stack[-1].children.append(node)
        stack.append(node)
    version = head.path_val("GEDC", "VERS") if head else None
    if head is None:
        warnings.append("No HEAD record found — this may not be a GEDCOM file.")
    if not trailer:
        warnings.append("No TRLR (end-of-file) record — the file may be truncated.")
    return GedcomFile(head, records, codec, declared, version, len(lines), failures, warnings, trailer)


def detect_product(head: Node | None) -> dict:
    """Identify the exporting program and tree from the header (used to suggest the import lineage)."""
    if head is None:
        return {"product": "other", "source": None}
    sour = head.first("SOUR")
    src = (sour.value if sour else "") or ""
    name = sour.val("NAME") if sour else None
    vers = sour.val("VERS") if sour else None
    corp = sour.val("CORP") if sour else None
    blob = " ".join(x for x in [src, name or "", corp or ""] if x).lower()
    if "ancestry" in blob:
        product = "ancestry"
    elif "rootsmagic" in blob:
        product = "rootsmagic"
    elif "ftm" in blob.split() or "family tree maker" in blob or "mackiev" in blob or src.upper().startswith("FTM"):
        product = "ftm"
    else:
        product = "other"
    tree = sour.first("_TREE") if sour else None
    tree_name = tree.value if tree is not None and tree.value else None
    tree_id = (tree.val("RIN") if tree is not None else None) or (tree.val("_ENV") if tree is not None else None)
    return {"product": product, "source": src or None, "source_name": name, "source_version": vers, "corp": corp,
            "tree_name": tree_name, "tree_id": tree_id, "tree_description": tree.val("NOTE") if tree is not None else None,
            "file_name": head.val("FILE"),
            "export_date": head.val("DATE"), "language": head.val("LANG")}
