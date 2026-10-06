"""Read a family-tree box chart saved as PDF (e.g. Family Tree Maker's ancestor chart) and turn it into GEDCOM.

In a box chart the *relationships are the drawn lines*, not the text, so this reads the page geometry:

* each person box is a filled rectangle; its text lines are the people in it ("Mr./Ms. Name" lines in a large
  font, followed by small "Born: / Married: / Died:" lines);
* a box with several people is an ancestor followed by their brothers and sisters (Family Tree Maker lists the
  direct ancestor first);
* connector lines run from the top/bottom edge of a child's box to the left edge of each parent's box — the
  parent drawn higher is the father, the lower one the mother;
* the same couple can appear more than once (pedigree collapse); boxes with identical text and identical
  ancestry are merged into one person.

Everything read from the chart is recorded with its position, and nothing is guessed: if a relationship line
can't be traced it is reported, not invented. The result is plain GEDCOM, so it goes through the normal import
preview, project and undo.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                       "october", "november", "december"], 1)}
GED_MON = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


class ChartError(Exception):
    pass


@dataclass
class Person:
    key: str
    name: str                      # as printed, without Mr./Ms.
    sex: str | None
    facts: list = field(default_factory=list)      # (tag, date_text, place)
    note: str | None = None        # e.g. a religious name in parentheses
    box: int = 0
    row: int = 0
    given: str = ""
    surname: str = ""


@dataclass
class Box:
    idx: int
    x0: float
    y0: float
    x1: float
    y1: float
    people: list = field(default_factory=list)
    father: int | None = None
    mother: int | None = None


@dataclass
class Chart:
    title: str | None
    producer: str | None
    created: str | None
    boxes: list
    people: dict           # key -> Person
    families: list         # dicts: husb, wife, children, marr (date, place)
    warnings: list
    merged: list           # (kept key, merged key) for pedigree collapse


# ------------------------------------------------------------------ geometry extraction

def _mul(a, b):
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3], a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def _ap(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def _geometry(page, reader):
    from pypdf.generic import ContentStream
    cs = ContentStream(page.get_contents(), reader)
    ctm, stack, path, cur = [1, 0, 0, 1, 0, 0], [], [], None
    fills, strokes, texts = [], [], []
    tm, size = None, 0.0
    for operands, op in cs.operations:
        if op == b"INLINE IMAGE":
            continue
        if op == b"q":
            stack.append(ctm[:])
        elif op == b"Q":
            ctm = stack.pop() if stack else [1, 0, 0, 1, 0, 0]
        elif op == b"cm":
            ctm = _mul([float(x) for x in operands], ctm)
        elif op == b"m":
            cur = [_ap(ctm, float(operands[0]), float(operands[1]))]
            path.append(cur)
        elif op == b"l" and cur is not None:
            cur.append(_ap(ctm, float(operands[0]), float(operands[1])))
        elif op == b"re":
            x, y, w, h = (float(v) for v in operands)
            path.append([_ap(ctm, x, y), _ap(ctm, x + w, y), _ap(ctm, x + w, y + h), _ap(ctm, x, y + h), _ap(ctm, x, y)])
        elif op == b"h" and cur:
            cur.append(cur[0])
        elif op in (b"S", b"s"):
            strokes += [sp for sp in path if len(sp) >= 2]
            path, cur = [], None
        elif op in (b"B", b"B*", b"f", b"f*", b"F", b"b", b"b*"):
            fills += [sp for sp in path if len(sp) >= 3]
            path, cur = [], None
        elif op == b"n":
            path, cur = [], None
        elif op == b"Tf":
            size = float(operands[1])
        elif op == b"Tm":
            tm = [float(v) for v in operands]
        elif op in (b"Tj", b"TJ") and tm is not None:
            m = _mul(tm, ctm)
            s = operands[0]
            if op == b"TJ":
                s = "".join(str(x) for x in s if isinstance(x, str) or hasattr(x, "original_bytes") or isinstance(x, (bytes,)) and not isinstance(x, (int, float)))
            texts.append({"x": m[4], "y": m[5], "t": str(s), "size": size * abs(m[3]) or size})
    return fills, strokes, texts


def _bbox(sp):
    xs = [p[0] for p in sp]
    ys = [p[1] for p in sp]
    return min(xs), min(ys), max(xs), max(ys)


# ------------------------------------------------------------------ text → people

_NAME = re.compile(r"^(Mr|Ms|Mrs|Miss|Dr|Rev)\.?\s+(.+)$")
_FACT = re.compile(r"^(Born|Married|Died|Buried|Christened|Baptized|Baptised):\s*(.*)$")
FACT_TAGS = {"Born": "BIRT", "Married": "MARR", "Died": "DEAT", "Buried": "BURI", "Christened": "CHR", "Baptized": "BAPM", "Baptised": "BAPM"}


def _split_fact(v: str) -> tuple[str | None, str | None]:
    v = v.strip()
    if v.lower().startswith("in "):
        return None, v[3:].strip() or None
    m = re.match(r"^(.*?)\s+in\s+(.+)$", v)
    if m:
        return m.group(1).strip() or None, m.group(2).strip() or None
    return (v or None), None


def ged_date(text: str | None) -> str | None:
    """'February 13, 1945' → '13 FEB 1945'; 'October 1874' → 'OCT 1874'; '1906' → '1906'. Anything else is kept as a phrase."""
    if not text:
        return None
    t = text.strip().rstrip(".")
    m = re.match(r"^([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{3,4}(?:/\d{2})?)$", t)
    if m and m.group(1).lower() in MONTHS:
        return f"{int(m.group(2))} {GED_MON[MONTHS[m.group(1).lower()]]} {m.group(3)}"
    m = re.match(r"^([A-Za-z]+)\.?\s+(\d{3,4}(?:/\d{2})?)$", t)
    if m and m.group(1).lower() in MONTHS:
        return f"{GED_MON[MONTHS[m.group(1).lower()]]} {m.group(2)}"
    m = re.match(r"^(abt|about|bef|before|aft|after|est|cal)\.?\s+(.+)$", t, re.IGNORECASE)
    if m:
        inner = ged_date(m.group(2))
        q = {"abt": "ABT", "about": "ABT", "bef": "BEF", "before": "BEF", "aft": "AFT", "after": "AFT", "est": "EST", "cal": "CAL"}[m.group(1).lower()]
        return f"{q} {inner}" if inner and not inner.startswith("(") else f"({t})"
    if re.match(r"^\d{3,4}$", t):
        return t
    return f"({t})"


def _box_people(box: Box, texts: list) -> list:
    """Group the text lines inside a box into people (name line + fact lines); join wrapped lines."""
    lines = sorted((t for t in texts if box.x0 - 3 <= t["x"] <= box.x1 + 3 and box.y0 - 1 <= t["y"] <= box.y1 + 1),
                   key=lambda t: (-round(t["y"], 1), t["x"]))
    if not lines:
        return []
    big = max(t["size"] for t in lines)
    out: list = []
    last_kind = None
    for t in lines:
        s = t["t"].strip()
        if not s:
            continue
        if t["size"] >= big * 0.8:            # a name line (or the wrapped end of one)
            m = _NAME.match(s)
            if m:
                out.append({"title": m.group(1), "name": m.group(2).strip(), "facts": [], "y": t["y"]})
                last_kind = "name"
            elif out and last_kind == "name":
                prev = out[-1]["name"]
                out[-1]["name"] = (prev + s) if prev.endswith("-") else f"{prev} {s}"
            continue
        if not out:
            continue
        m = _FACT.match(s)
        if m:
            out[-1]["facts"].append([m.group(1), m.group(2)])
            last_kind = "fact"
        elif last_kind == "fact" and out[-1]["facts"]:
            f = out[-1]["facts"][-1]
            f[1] = f"{f[1]} {s}".strip()      # wrapped place ("…, Quebec," / "Canada")
    return out


_PARTICLES = {"st.", "ste.", "st", "ste", "saint", "sainte", "de", "du", "des", "la", "le", "van", "von", "der", "mac", "o'", "dit"}


def split_name(full: str, known_surnames: set) -> tuple[str, str]:
    """'Marie Louise St. Onge' → ('Marie Louise', 'St. Onge'); 'Pierre Lavoie dit Lafleur' → ('Pierre', 'Lavoie dit Lafleur')."""
    toks = full.split()
    if len(toks) == 1:
        return "", toks[0]
    # longest known surname that ends the name
    for k in range(min(4, len(toks) - 1), 0, -1):
        cand = " ".join(toks[-k:])
        if cand.lower() in known_surnames and not (len(toks) > k and toks[-k - 1].lower() in ("dit", "st.", "ste.", "de")):
            return " ".join(toks[:-k]), cand
    i = len(toks) - 1
    while i > 1 and (toks[i - 1].lower() in _PARTICLES or toks[i - 1].endswith("-")):
        i -= 1
    if i >= 2 and toks[i].lower() == "dit":
        i -= 1    # "Lavoie dit Lafleur": the name before "dit" is part of the surname
    return " ".join(toks[:i]), " ".join(toks[i:])


# ------------------------------------------------------------------ main parse

def parse_pdf(data: bytes) -> Chart:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise ChartError("Reading PDF files needs the 'pypdf' package (pip install pypdf).") from e
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise ChartError(f"This PDF could not be read ({type(e).__name__}).") from e
    if reader.is_encrypted:
        raise ChartError("This PDF is password-protected.")
    meta = reader.metadata or {}
    boxes_all, warnings = [], []
    people: dict = {}
    families: list = []
    page_boxes = []
    chart_title = None
    for pno, page in enumerate(reader.pages):
        fills, strokes, texts = _geometry(page, reader)
        if not texts:
            continue
        title_size = max(t["size"] for t in texts)
        body = [t for t in texts if t["size"] < title_size * 0.6] if title_size > 30 else texts
        if title_size > 30 and chart_title is None:
            # the big heading; often drawn one character at a time
            head = sorted((t for t in texts if t["size"] >= title_size * 0.9), key=lambda t: (-round(t["y"]), t["x"]))
            chart_title = re.sub(r"\s+", " ", "".join(t["t"] for t in head)).strip() or None
        rects = []
        for sp in fills:
            x0, y0, x1, y1 = _bbox(sp)
            if (x1 - x0) > 40 and (y1 - y0) > 12 and (x1 - x0) < 1500 and (y1 - y0) < 1500:
                rects.append((x0, y0, x1, y1))
        boxes = []
        for (x0, y0, x1, y1) in sorted(set(rects), key=lambda b: (b[0], -b[3])):
            b = Box(len(boxes_all) + len(boxes), x0, y0, x1, y1)
            b.people = _box_people(b, body)
            if b.people:
                boxes.append(b)
        _link(boxes, strokes, warnings)
        page_boxes.append(boxes)
        boxes_all += boxes
    if not boxes_all:
        raise ChartError("No family-tree boxes were found in this PDF. It may be a scanned image or a report layout this importer doesn't read yet.")
    title = chart_title or next((str(t) for t in [meta.get("/Title")] if t and str(t).strip().lower() not in ("family tree maker", "untitled")), None)
    # people
    pid = 0
    box_people: dict = {}
    for b in boxes_all:
        keys = []
        for i, pr in enumerate(b.people):
            pid += 1
            nm = pr["name"]
            note = None
            m = re.match(r"^(.*?)\s*\((.+)\)\s*$", nm)
            if m:
                nm, note = m.group(1).strip(), m.group(2).strip()
            sex = "M" if pr["title"] in ("Mr", "Rev") else "F" if pr["title"] in ("Ms", "Mrs", "Miss") else None
            p = Person(f"P{pid}", nm, sex, [(FACT_TAGS[k], *_split_fact(v)) for k, v in pr["facts"]], note, b.idx, i)
            people[p.key] = p
            keys.append(p.key)
        box_people[b.idx] = keys
    # surnames: learn from fathers (a child's surname is usually the father's)
    known = set()
    for b in boxes_all:
        for k in box_people[b.idx]:
            toks = people[k].name.split()
            if len(toks) >= 2:
                known.add(toks[-1].lower())
                if toks[-2].lower() in _PARTICLES:
                    known.add(" ".join(toks[-2:]).lower())
    for p in people.values():
        p.given, p.surname = split_name(p.name, known)
    # families from the lines: the first person in a box is the ancestor; everyone in the box shares the parents
    by_idx = {b.idx: b for b in boxes_all}
    fam_index: dict = {}
    for b in boxes_all:
        if b.father is None and b.mother is None:
            continue
        husb = box_people[b.father][0] if b.father is not None else None
        wife = box_people[b.mother][0] if b.mother is not None else None
        k = (husb, wife)
        if k not in fam_index:
            fam_index[k] = {"husb": husb, "wife": wife, "children": [], "marr": None}
            families.append(fam_index[k])
        fam_index[k]["children"] += box_people[b.idx]
    # marriages: printed in a spouse's own box; attach to the family where that person is a parent
    for p in people.values():
        for tag, d, pl in p.facts:
            if tag != "MARR":
                continue
            fam = next((f for f in families if p.key in (f["husb"], f["wife"])), None)
            if fam is None:
                fam = {"husb": p.key if p.sex == "M" else None, "wife": p.key if p.sex != "M" else None, "children": [], "marr": None}
                families.append(fam)
            if fam["marr"] is None:
                fam["marr"] = (d, pl)
    merged = _collapse(people, families, box_people)
    # A child's surname is usually the father's: use it to split compound names ("Madeleine Lefebvre Boulanger")
    for f in families:
        fa = people.get(f["husb"]) if f["husb"] else None
        if not fa or not fa.surname:
            continue
        first = fa.surname.split()[0].lower()
        for c in f["children"]:
            cp = people.get(c)
            if not cp:
                continue
            toks = cp.name.split()
            low = [t.lower().rstrip("-") for t in toks]
            if first in low and low.index(first) > 0:
                i = low.index(first)
                cp.given, cp.surname = " ".join(toks[:i]), " ".join(toks[i:])
    for b in boxes_all:
        if len(b.people) > 1 and b.father is None and b.mother is None:
            warnings.append(f"No parents drawn for the box starting with {b.people[0]['name']} — its {len(b.people) - 1} other "
                            "people were imported as brothers and sisters without parents.")
    return Chart(title, str(meta.get("/Producer") or "") or None, str(meta.get("/CreationDate") or "") or None,
                 boxes_all, people, families, warnings, merged)


def _internal(bx, a, b, pad=4) -> bool:
    def near(p):
        return bx.x0 - pad <= p[0] <= bx.x1 + pad and bx.y0 - pad <= p[1] <= bx.y1 + pad

    def on_edge(p):
        return min(abs(p[0] - bx.x0), abs(p[0] - bx.x1), abs(p[1] - bx.y0), abs(p[1] - bx.y1)) <= pad

    if not (near(a) and near(b)):
        return False
    return (on_edge(a) and on_edge(b)) or (not on_edge(a) and not on_edge(b))


def _link(boxes: list, strokes: list, warnings: list) -> None:
    """Trace connector lines: join segments into polylines and find which boxes each one touches."""
    segs = []
    for sp in strokes:
        for a, b in zip(sp, sp[1:]):
            if a == b:
                continue
            # ignore box frames and separators drawn inside a box; keep connector stubs that run into a box
            if any(_internal(bx, a, b) for bx in boxes):
                continue
            segs.append((a, b))
    # union segments that share an endpoint
    parent = list(range(len(segs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    ends: dict = {}
    for i, (a, b) in enumerate(segs):
        for pt in (a, b):
            k = (round(pt[0]), round(pt[1]))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    j = ends.get((k[0] + dx, k[1] + dy))
                    if j is not None:
                        parent[find(i)] = find(j)
            ends[k] = i
    groups: dict = {}
    for i in range(len(segs)):
        groups.setdefault(find(i), []).append(segs[i])
    tol = 8
    for g in groups.values():
        pts = [p for s in g for p in s]
        edge_touch, parents = [], []
        for bx in boxes:
            for (x, y) in pts:
                if bx.x0 - 2 <= x <= bx.x1 + 2 and (abs(y - bx.y0) <= tol or abs(y - bx.y1) <= tol):
                    edge_touch.append(bx)
                if abs(x - bx.x0) <= tol and bx.y0 - 2 <= y <= bx.y1 + 2:
                    parents.append(bx)
        child = None
        if parents:
            # the child's box sits to the left of the parent's (columns overlap, so compare with its left edge)
            left = [bx for bx in edge_touch if bx.x0 <= parents[0].x0 + 5 and all(bx is not q for q in parents)]
            child = max(left, key=lambda bx: bx.x0) if left else None
        uniq = []
        for p in parents:
            if p is not child and all(p is not q for q in uniq):
                uniq.append(p)
        parents = uniq
        if child and len(parents) == 1:
            pb = parents[0]
            title = pb.people[0]["title"] if pb.people else ""
            male = title in ("Mr", "Rev") if title in ("Mr", "Rev", "Ms", "Mrs", "Miss") else (pb.y0 + pb.y1) / 2 > (child.y0 + child.y1) / 2
            if male and child.father is None:
                child.father = pb.idx
            elif not male and child.mother is None:
                child.mother = pb.idx
            else:
                warnings.append(f"Two {'fathers' if male else 'mothers'} drawn for {child.people[0]['name']}; kept the first.")
        elif child and len(parents) > 1:
            warnings.append(f"A connector from {child.people[0]['name']} touches several boxes; it was not used.")


def _collapse(people: dict, families: list, box_people: dict) -> list:
    """Merge repeated ancestors (pedigree collapse). Two entries are the same person when their printed text is
    identical and includes at least one date or place, and their parents (where drawn) don't conflict.
    A wife is merged too when her husband was merged and she is printed identically. Names alone never merge."""
    merged: list = []

    def text_sig(k):
        p = people[k]
        return (p.name, p.sex, tuple(p.facts), p.note)

    def parents(k):
        for f in families:
            if k in f["children"]:
                return f["husb"], f["wife"]
        return None, None

    def compatible(a, b):
        pa, pb = parents(a), parents(b)
        return all(x is None or y is None or x == y for x, y in zip(pa, pb))

    def merge(a, b):
        for f in families:
            f["husb"] = a if f["husb"] == b else f["husb"]
            f["wife"] = a if f["wife"] == b else f["wife"]
            f["children"] = list(dict.fromkeys(a if c == b else c for c in f["children"]))
        people.pop(b, None)
        merged.append((a, b))

    changed = True
    while changed:
        changed = False
        groups: dict = {}
        for k in list(people):
            p = people[k]
            if any(d or pl for _, d, pl in p.facts):
                groups.setdefault(text_sig(k), []).append(k)
        for ks in groups.values():
            keep = ks[0]
            for other in ks[1:]:
                if other in people and keep in people and compatible(keep, other):
                    merge(keep, other)
                    changed = True
        # spouses printed identically on two copies of the same family
        for f in families:
            for g in families:
                if f is g:
                    continue
                for role, other in (("husb", "wife"), ("wife", "husb")):
                    if f[role] and f[role] == g[role] and f[other] and g[other] and f[other] != g[other] \
                            and f[other] in people and g[other] in people and people[f[other]].name == people[g[other]].name \
                            and (not people[f[other]].facts or not people[g[other]].facts or text_sig(f[other]) == text_sig(g[other])) \
                            and compatible(f[other], g[other]):
                        merge(f[other], g[other])
                        changed = True
        # identical families after merging
        out, seen = [], {}
        for f in families:
            k = (f["husb"], f["wife"])
            if (f["husb"] or f["wife"]) and k in seen:
                g = seen[k]
                g["children"] = list(dict.fromkeys(g["children"] + f["children"]))
                g["marr"] = g["marr"] or f["marr"]
                changed = True
            else:
                seen[k] = f
                out.append(f)
        # a one-parent family whose parent also heads a two-parent family is the same family
        final = []
        for f in out:
            if f["marr"] is not None and not f["children"] and (f["husb"] is None or f["wife"] is None):
                lone = f["husb"] or f["wife"]
                if any(g is not f and lone in (g["husb"], g["wife"]) for g in out):
                    tgt = next(g for g in out if g is not f and lone in (g["husb"], g["wife"]))
                    tgt["marr"] = tgt["marr"] or f["marr"]
                    continue
            final.append(f)
        families[:] = final
    return merged


# ------------------------------------------------------------------ GEDCOM output

def to_gedcom(chart: Chart, source_name: str) -> str:
    lines = ["0 HEAD", "1 SOUR KindredCompassPDF", "2 NAME Kindred Compass PDF chart reader", "1 GEDC", "2 VERS 5.5.1", "2 FORM LINEAGE-LINKED",
             "1 CHAR UTF-8", f"1 FILE {source_name}", "1 NOTE Converted from a family-tree chart saved as PDF"
             + (f" ({chart.producer}{', ' + chart.title if chart.title else ''})" if chart.producer or chart.title else ""),
             "0 @S1@ SOUR", f"1 TITL Family tree chart: {source_name}"]
    if chart.title:
        lines.append(f"1 AUTH {chart.title}")
    if chart.created:
        lines.append(f"1 NOTE PDF created {chart.created}")
    fam_of_child: dict = {}
    fam_of_spouse: dict = {}
    for i, f in enumerate(chart.families, 1):
        for c in f["children"]:
            fam_of_child.setdefault(c, []).append(i)
        for s in (f["husb"], f["wife"]):
            if s:
                fam_of_spouse.setdefault(s, []).append(i)

    def cite(level):
        return [f"{level} SOUR @S1@"]
    for k, p in chart.people.items():
        lines.append(f"0 @{k}@ INDI")
        lines.append(f"1 NAME {p.given} /{p.surname}/".replace("  ", " "))
        if p.given:
            lines.append(f"2 GIVN {p.given}")
        if p.surname:
            lines.append(f"2 SURN {p.surname}")
        if p.note:
            lines.append(f"2 NICK {p.note}")
        lines += cite(2)
        if p.sex:
            lines.append(f"1 SEX {p.sex}")
        for tag, d, pl in p.facts:
            if tag == "MARR":
                continue
            lines.append(f"1 {tag}" + ("" if d or pl else " Y"))
            if d:
                lines.append(f"2 DATE {ged_date(d)}")
            if pl:
                lines.append(f"2 PLAC {pl}")
            lines += cite(2)
        if p.note:
            lines.append(f"1 NOTE Also printed as “{p.note}” on the chart")
        for fi in fam_of_child.get(k, []):
            lines.append(f"1 FAMC @F{fi}@")
        for fi in fam_of_spouse.get(k, []):
            lines.append(f"1 FAMS @F{fi}@")
    for i, f in enumerate(chart.families, 1):
        lines.append(f"0 @F{i}@ FAM")
        if f["husb"]:
            lines.append(f"1 HUSB @{f['husb']}@")
        if f["wife"]:
            lines.append(f"1 WIFE @{f['wife']}@")
        for c in f["children"]:
            lines.append(f"1 CHIL @{c}@")
        if f["marr"]:
            d, pl = f["marr"]
            lines.append("1 MARR" + ("" if d or pl else " Y"))
            if d:
                lines.append(f"2 DATE {ged_date(d)}")
            if pl:
                lines.append(f"2 PLAC {pl}")
            lines += cite(2)
    lines.append("0 TRLR")
    return "\n".join(lines) + "\n"


def summary(chart: Chart) -> dict:
    return {"people": len(chart.people), "families": len(chart.families), "boxes": len(chart.boxes),
            "merged_repeats": len(chart.merged), "warnings": chart.warnings}
