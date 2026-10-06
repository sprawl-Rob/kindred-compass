"""Map a parsed GEDCOM file into a neutral model of people, families, facts, sources and media.

Deterministic and AI-free. Anything not mapped is counted in `unsupported` (with tag
paths and line numbers) and kept in the original record, never silently dropped.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .gdates import parse_gedcom_date
from .parser import GedcomFile, Node

# GEDCOM tag → (claim_type, label)
INDI_EVENTS = {
    "BIRT": ("birth", "Birth"), "CHR": ("baptism", "Christening"), "BAPM": ("baptism", "Baptism"), "CHRA": ("baptism", "Adult christening"),
    "DEAT": ("death", "Death"), "BURI": ("burial", "Burial"), "CREM": ("burial", "Cremation"),
    "RESI": ("residence", "Residence"), "CENS": ("residence", "Census"), "IMMI": ("immigration", "Immigration"),
    "EMIG": ("emigration", "Emigration"), "NATU": ("naturalization", "Naturalization"), "OCCU": ("occupation", "Occupation"),
    "RELI": ("religion", "Religion"), "MILI": ("military", "Military"), "_MILT": ("military", "Military service"),
    "_MIL": ("military", "Military service"), "PROP": ("property", "Property"), "PROB": ("other", "Probate"), "WILL": ("other", "Will"),
    "EDUC": ("other", "Education"), "GRAD": ("other", "Graduation"), "ADOP": ("other", "Adoption"), "BARM": ("other", "Bar mitzvah"),
    "BASM": ("other", "Bat mitzvah"), "BLES": ("other", "Blessing"), "CONF": ("other", "Confirmation"), "FCOM": ("other", "First communion"),
    "ORDN": ("other", "Ordination"), "RETI": ("other", "Retirement"), "NATI": ("other", "Nationality"), "TITL": ("other", "Title"),
    "DSCR": ("other", "Physical description"), "SSN": ("other", "Social Security number"), "IDNO": ("other", "Identification number"),
    "CAST": ("other", "Caste"), "NCHI": ("other", "Number of children"), "NMR": ("other", "Number of marriages"),
    "EVEN": ("other", "Event"), "FACT": ("other", "Fact"), "_DEG": ("other", "Degree"), "_ELEC": ("other", "Elected"),
    "_EMPLOY": ("occupation", "Employment"), "_MILTID": ("military", "Military ID"), "_MDCL": ("other", "Medical"), "_HEIG": ("other", "Height"), "_WEIG": ("other", "Weight"),
    "_EXCM": ("other", "Excommunication"), "_FUN": ("other", "Funeral"), "_DCAUSE": ("other", "Cause of death"),
}
FAM_EVENTS = {
    "MARR": ("marriage", "Marriage"), "DIV": ("divorce", "Divorce"), "DIVF": ("divorce", "Divorce filed"), "ANUL": ("divorce", "Annulment"),
    "ENGA": ("other", "Engagement"), "MARB": ("other", "Marriage banns"), "MARC": ("other", "Marriage contract"),
    "MARL": ("other", "Marriage licence"), "MARS": ("other", "Marriage settlement"), "EVEN": ("other", "Family event"),
    "RESI": ("residence", "Family residence"), "CENS": ("residence", "Family census"), "_SEPR": ("other", "Separation"),
}
NAME_TYPES = {"BIRTH": "birth", "AKA": "alias", "AKAN": "alias", "IMMIGRANT": "anglicized", "MAIDEN": "maiden", "MARRIED": "married",
              "PROFESSIONAL": "alias", "OTHER": "variant", "NICKNAME": "alias", "ALSO KNOWN AS": "alias"}
PEDI = {"BIRTH": "biological", "NATURAL": "biological", "BIOLOGICAL": "biological", "ADOPTED": "adopted", "STEP": "step",
        "FOSTER": "foster", "GUARDIAN": "guardian", "SEALED": "sealed", "SEALING": "sealed", "UNKNOWN": "unknown", "PRIVATE": "unknown",
        "CHALLENGED": "other", "DISPROVEN": "other", "RELATED": "other", "OTHER": "other"}
# Ancestry writes EVEN + TYPE for some migration events.
EVEN_TYPES = {"arrival": ("immigration", "Arrival"), "departure": ("emigration", "Departure"), "immigration": ("immigration", "Immigration"),
              "emigration": ("emigration", "Emigration"), "naturalizationpetition": ("naturalization", "Naturalization petition"),
              "naturalization": ("naturalization", "Naturalization"), "census": ("residence", "Census")}
# Media-record metadata written by Ancestry/FTM; preserved in the original record and reported as understood.
OBJE_KNOWN = {"FILE", "FORM", "TITL", "NOTE", "SOUR", "RIN", "REFN", "CHAN", "DATE", "PLAC", "_DSCR", "_META", "_CREA", "_USER", "_CLON",
              "_ORIG", "_ATL", "_DATE", "_TEXT", "_PRIM", "_CROP", "_TYPE", "_MTYPE", "_STYPE", "_SIZE", "_WDTH", "_HGHT", "CREA", "UID", "_UID"}

# Tags understood inside each context (others are reported as unsupported).
EVENT_DETAIL = {"DATE", "PLAC", "TYPE", "AGE", "CAUS", "NOTE", "SOUR", "OBJE", "ADDR", "AGNC", "RELI", "RESN", "PHON", "EMAIL", "WWW",
                "_PRIM", "_SDATE", "_DATE2", "_PLAC2", "_DESC", "_DESCRIPTION"}
INDI_KNOWN = set(INDI_EVENTS) | {"NAME", "SEX", "FAMC", "FAMS", "NOTE", "SOUR", "OBJE", "_UID", "UID", "RIN", "REFN", "CHAN",
                                 "RESN", "_PHOTO", "_PRIMARY", "_MARNM", "AFN", "ASSO", "ALIA", "EXID", "CREA", "FSID", "_FSFTID"}
FAM_KNOWN = set(FAM_EVENTS) | {"HUSB", "WIFE", "CHIL", "NOTE", "SOUR", "OBJE", "_UID", "UID", "RIN", "REFN", "CHAN", "NCHI", "RESN",
                               "_STAT", "_MSTAT", "EXID", "CREA"}
SOUR_KNOWN = {"TITL", "AUTH", "PUBL", "ABBR", "TEXT", "REPO", "NOTE", "OBJE", "DATA", "_APID", "RIN", "REFN", "CHAN", "_UID", "UID", "CALN",
              "WWW", "_TMPLT", "_BIBL", "_FOOT", "_SUBQ", "EXID", "CREA", "_TYPE", "_MEDI"}
CITE_KNOWN = {"PAGE", "DATA", "QUAY", "NOTE", "OBJE", "_APID", "EVEN", "_LINK", "WWW", "_TMPLT", "_FOOT", "_SUBQ", "_BIBL", "TEXT", "_JUST",
              "_HPID", "_WPID"}   # _HPID/_WPID: Ancestry husband/wife person references on couple-event citations (kept verbatim)

COUNTRIES = {"usa", "united states", "united states of america", "us", "u.s.a.", "england", "scotland", "wales", "ireland", "northern ireland",
             "united kingdom", "canada", "australia", "new zealand", "germany", "deutschland", "norway", "sweden", "denmark", "france",
             "italy", "netherlands", "poland", "russia", "austria", "switzerland", "mexico", "prussia", "hungary", "czech republic",
             "ukraine", "finland", "belgium", "spain", "portugal", "greece", "lithuania", "latvia", "slovakia"}
US_STATES = {"alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida", "georgia", "hawaii",
             "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
             "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york",
             "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
             "south dakota", "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming",
             "district of columbia"}


def clean(v: str | None) -> str:
    if not v:
        return ""
    return v.replace("@@", "@").strip()


def is_pointer(v: str | None) -> bool:
    return bool(v) and bool(re.fullmatch(r"@[^@\s]+@", v.strip()))


def subtree_hash(n: Node) -> str:
    def norm(x: Node):
        return [x.tag, x.value, [norm(c) for c in x.children if c.tag not in ("CHAN",)]]
    return hashlib.sha256(json.dumps(norm(n), ensure_ascii=False).encode()).hexdigest()[:20]


def node_json(n: Node) -> dict:
    return n.to_dict()


def split_place(text: str) -> dict:
    """Conservative jurisdiction split. The full original string is always kept as `name`."""
    t = clean(text)
    parts = [p.strip() for p in t.split(",") if p.strip()]
    out = {"name": t}
    if not parts:
        return out
    last = parts[-1].lower()
    if last in COUNTRIES:
        country = "United States" if last in ("usa", "united states of america", "us", "u.s.a.", "united states") else parts[-1]
        out["country"] = country
        rest = parts[:-1]
        if country == "United States" and rest and rest[-1].lower() in US_STATES:
            out["region"] = rest[-1]
            rest = rest[:-1]
            if len(rest) >= 2:
                out["county"] = rest[-1].removesuffix(" County").removesuffix(" Co.")
                out["municipality"] = rest[0]
            elif len(rest) == 1:
                # one element left: could be a town or a county; only call it a county if it says so
                if rest[0].lower().endswith(" county"):
                    out["county"] = rest[0][:-7]
                else:
                    out["municipality"] = rest[0]
        elif rest:
            out["region"] = rest[-1]
            if len(rest) >= 2:
                out["municipality"] = rest[0]
    elif last in US_STATES:
        out["country"] = "United States"
        out["region"] = parts[-1]
        rest = parts[:-1]
        if len(rest) >= 2:
            out["county"] = rest[-1].removesuffix(" County")
            out["municipality"] = rest[0]
        elif rest:
            out["municipality"] = rest[0]
    return out


@dataclass
class Citation:
    sour_xref: str | None
    title: str
    page: str
    text: str
    quay: str | None
    apid: str | None
    notes: list
    media: list
    node: Node
    path: str
    links: list = field(default_factory=list)

    @property
    def key(self) -> str:
        return "cite:" + hashlib.sha256(json.dumps([self.sour_xref, self.title if not self.sour_xref else "", self.page, self.apid, self.text],
                                                   ensure_ascii=False).encode()).hexdigest()[:20]


@dataclass
class Fact:
    tag: str
    claim_type: str
    label: str
    date_text: str
    date: dict
    place: dict | None
    value: str
    type_text: str
    age: str
    cause: str
    notes: list
    citations: list
    media: list
    node: Node
    custom: bool = False
    primary: bool = False

    @property
    def key(self) -> str:
        return "fact:" + hashlib.sha256(json.dumps([self.tag, self.type_text, self.date_text, (self.place or {}).get("name", ""), self.value],
                                                   ensure_ascii=False).encode()).hexdigest()[:20]


@dataclass
class Name:
    name_type: str
    given: str
    surname: str
    full: str
    suffix: str
    prefix: str
    nickname: str
    script: str | None
    language: str | None
    note: str
    citations: list
    node: Node

    @property
    def key(self) -> str:
        return "name:" + "|".join([self.name_type, self.given, self.surname, self.full]).lower()


@dataclass
class Person:
    xref: str
    stable_keys: list
    names: list
    sex: str | None
    facts: list
    notes: list
    citations: list
    media: list
    famc: list            # [(fam_xref, pedi_label_or_None, raw_pedi)]
    fams: list
    node: Node
    living_hint: str = "unknown"

    @property
    def display_name(self) -> str:
        if not self.names:
            return "(no name recorded)"
        n = self.names[0]
        return " ".join(x for x in [n.prefix, n.given, n.surname, n.suffix] if x).strip() or n.full or "(no name recorded)"


@dataclass
class Family:
    xref: str
    husb: str | None
    wife: str | None
    children: list        # [{xref, frel, mrel, raw_frel, raw_mrel}]
    facts: list
    notes: list
    citations: list
    media: list
    node: Node
    stable_keys: list = field(default_factory=list)


@dataclass
class Model:
    people: dict
    families: dict
    sources: dict          # xref → {title, author, publ, abbr, text, repo, apid, notes, media, node}
    repositories: dict
    notes: dict
    objects: dict          # OBJE records
    unsupported: Counter
    unsupported_examples: dict
    vendor_mapped: Counter
    warnings: list
    media_refs: list       # [{owner_kind, owner_xref, file, form, title, obje_xref, path, node}]
    citations: dict        # key → Citation (unique)


def build(g: GedcomFile) -> Model:
    recs = g.by_xref()
    unsupported: Counter = Counter()
    vendor_mapped: Counter = Counter()
    examples: dict = {}
    warnings: list = []
    media_refs: list = []
    citations: dict = {}

    def unsup(path: str, n: Node):
        unsupported[path] += 1
        examples.setdefault(path, {"line": n.line, "text": (n.raw[0][1] if n.raw else "")[:160]})

    notes = {}
    repositories = {}
    objects = {}
    for r in g.records:
        if r.tag == "NOTE" and r.xref:
            notes[r.xref] = clean(r.value)
        elif r.tag == "REPO" and r.xref:
            repositories[r.xref] = {"name": clean(r.val("NAME")) or "(unnamed repository)", "address": clean(r.path_val("ADDR")),
                                    "www": clean(r.val("WWW")), "node": r}
        elif r.tag == "OBJE" and r.xref:
            objects[r.xref] = r

    def note_texts(n: Node, path: str) -> list:
        out = []
        for c in n.all("NOTE"):
            if is_pointer(c.value):
                t = notes.get(c.value.strip())
                if t is None:
                    warnings.append(f"Line {c.line}: note {c.value} is referenced but not defined.")
                else:
                    out.append(t)
            elif c.value:
                out.append(clean(c.value))
        return out

    def media_of(n: Node, owner_kind: str, owner_xref: str | None, path: str, extra_pointers: list | None = None) -> list:
        out = []
        for o in n.all("OBJE") + (extra_pointers or []):
            target = objects.get(o.value.strip()) if is_pointer(o.value) else o
            if target is None:
                warnings.append(f"Line {o.line}: media object {o.value} is referenced but not defined.")
                continue
            files = target.all("FILE")
            title = clean(target.val("TITL")) or clean(target.path_val("FILE", "TITL"))
            form = clean(target.val("FORM")) or clean(target.path_val("FILE", "FORM"))
            clon = target.first("_CLON")
            online_id = clean(target.val("RIN")) or (clean(clon.val("_OID")) if clon is not None else "")
            if not files:
                warnings.append(f"Line {target.line}: media object has no FILE reference.")
            for f in files:
                fm = f.first("FORM")
                mtype = clean(fm.val("_MTYPE")) if fm is not None else ""
                mtype = mtype or (clean(fm.val("TYPE")) if fm is not None else "")
                ref = {"owner_kind": owner_kind, "owner_xref": owner_xref, "file": clean(f.value), "form": clean(f.val("FORM")) or form,
                       "title": clean(f.val("TITL")) or title, "obje_xref": target.xref, "path": path, "line": f.line,
                       "oid": online_id, "media_type": mtype, "primary": (o.val("_PRIM") or "").upper() in ("Y", "YES"),
                       "node": target}
                media_refs.append(ref)
                out.append(ref)
            if target.xref:
                for c in target.children:
                    if c.tag not in OBJE_KNOWN:
                        unsup(f"OBJE.{c.tag}", c)
        return out

    def cites(n: Node, path: str) -> list:
        out = []
        for s in n.all("SOUR"):
            if is_pointer(s.value):
                xr = s.value.strip()
                src = recs.get(xr)
                if src is None:
                    warnings.append(f"Line {s.line}: source {xr} is referenced but not defined.")
                title = clean(src.val("TITL")) if src else xr
            else:
                xr, title = None, clean(s.value) or "(untitled source)"
            data = s.first("DATA")
            text = "\n".join(clean(t.value) for t in (data.all("TEXT") if data else []) + s.all("TEXT") if t.value)
            for c in s.children:
                if c.tag not in CITE_KNOWN:
                    unsup(f"{path}.SOUR.{c.tag}", c)
            apids = [clean(a.value) for a in s.all("_APID") if a.value]
            notes_ = note_texts(s, path + ".SOUR")
            if s.val("_JUST"):
                notes_.append("Justification: " + clean(s.val("_JUST")))
            links = [clean(x.value) for x in s.all("_LINK") + s.all("WWW") + (data.all("WWW") if data else []) if x.value]
            cit = Citation(xr, title or "(untitled source)", clean(s.val("PAGE")), text, s.val("QUAY"), "; ".join(apids) or None,
                           notes_, [], s, path + ".SOUR", links)
            cit.media = media_of(s, "citation", xr, path + ".SOUR")
            citations.setdefault(cit.key, cit)
            out.append(citations[cit.key])
        return out

    def fact(n: Node, table: dict, path: str, custom=False) -> Fact:
        ctype, label = table.get(n.tag, ("other", n.tag.lstrip("_").title()))
        if n.tag.startswith("_") and n.tag in table:
            vendor_mapped[f"{path}.{n.tag} → {label}"] += 1
        type_text = clean(n.val("TYPE"))
        if n.tag in ("EVEN", "FACT") and type_text:
            label = type_text
            mapped = EVEN_TYPES.get(re.sub(r"[^a-z]", "", type_text.lower()))
            if mapped and n.tag == "EVEN":
                ctype, label = mapped
        date_text = clean(n.val("DATE"))
        plac = n.first("PLAC")
        place = split_place(plac.value) if plac is not None and plac.value else None
        if place and plac is not None:
            mp = plac.first("MAP")
            if mp is not None:
                place["lat"], place["long"] = mp.val("LATI"), mp.val("LONG")
        for c in n.children:
            if c.tag not in EVENT_DETAIL:
                unsup(f"{path}.{n.tag}.{c.tag}", c)
        f = Fact(n.tag, ctype, label, date_text, parse_gedcom_date(date_text), place, clean(n.value) if not is_pointer(n.value) else "",
                 type_text, clean(n.val("AGE")), clean(n.val("CAUS")), note_texts(n, path + "." + n.tag), cites(n, f"{path}.{n.tag}"),
                 [], n, custom, primary=(n.val("_PRIM") or "").upper() in ("Y", "YES"))
        if f.value.upper() == "Y" and f.tag in INDI_EVENTS:
            f.value = ""   # "1 DEAT Y" just asserts the event happened
        if f.date.get("note"):
            f.notes.append(f.date["note"])
        dn = n.first("DATE")
        if dn is not None and dn.val("PHRASE"):
            f.notes.append("Date phrase: " + clean(dn.val("PHRASE")))
        return f

    people: dict = {}
    families: dict = {}
    sources: dict = {}
    for r in g.records:
        if r.tag == "INDI":
            if not r.xref:
                warnings.append(f"Line {r.line}: person record without an identifier was skipped.")
                continue
            names = []
            for nn in r.all("NAME"):
                raw = clean(nn.value)
                m = re.match(r"^(.*?)/(.*?)/(.*)$", raw)
                given, surname, suffix = (m.group(1).strip(), m.group(2).strip(), m.group(3).strip()) if m else (raw, "", "")
                given = clean(nn.val("GIVN")) or given
                surname = clean(nn.val("SURN")) or surname
                ntype = NAME_TYPES.get((nn.val("TYPE") or "").upper(), "birth" if not names else "variant")
                for c in nn.children:
                    if c.tag not in {"GIVN", "SURN", "NPFX", "NSFX", "NICK", "SPFX", "TYPE", "NOTE", "SOUR", "ROMN", "FONE", "TRAN", "_MARNM", "_AKA", "_PRIM"}:
                        unsup(f"INDI.NAME.{c.tag}", c)
                name = Name(ntype, given, surname, raw.replace("/", "").strip(), clean(nn.val("NSFX")) or suffix, clean(nn.val("NPFX")),
                            clean(nn.val("NICK")), None, None, "; ".join(note_texts(nn, "INDI.NAME")), cites(nn, "INDI.NAME"), nn)
                names.append(name)
                for alt_tag, label in (("ROMN", "romanized"), ("FONE", "phonetic"), ("TRAN", "translation")):
                    for alt in nn.all(alt_tag):
                        a = re.sub(r"/", "", clean(alt.value)).strip()
                        lang = clean(alt.val("LANG")) or None
                        names.append(Name("original_script" if alt_tag == "TRAN" else "variant", "", "", a, "", "", "", clean(alt.val("TYPE")) or None,
                                          lang, f"{label} form", [], alt))
                if nn.val("NICK"):
                    names.append(Name("alias", clean(nn.val("NICK")), surname, clean(nn.val("NICK")), "", "", "", None, None, "nickname", [], nn))
                for mn in nn.all("_MARNM"):
                    names.append(Name("married", given, clean(mn.value), f"{given} {clean(mn.value)}".strip(), "", "", "", None, None, "", [], mn))
            for mn in r.all("_MARNM"):
                first_given = names[0].given if names else ""
                names.append(Name("married", first_given, clean(mn.value), f"{first_given} {clean(mn.value)}".strip(), "", "", "", None, None, "", [], mn))
            facts = []
            for c in r.children:
                if c.tag in INDI_EVENTS:
                    facts.append(fact(c, INDI_EVENTS, "INDI"))
                elif c.tag.startswith("_") and c.tag not in INDI_KNOWN and (c.first("DATE") or c.first("PLAC")):
                    facts.append(fact(c, INDI_EVENTS, "INDI", custom=True))
                    unsup(f"INDI.{c.tag} (imported as a generic fact)", c)
                elif c.tag not in INDI_KNOWN:
                    unsup(f"INDI.{c.tag}", c)
            for f in facts:
                f.media = media_of(f.node, "person", r.xref, f"INDI.{f.tag}")
            stable = []
            for t in ("_UID", "UID", "RIN", "REFN", "AFN", "EXID", "FSID", "_FSFTID"):
                for c in r.all(t):
                    if c.value:
                        stable.append(f"{t}:{clean(c.value)}")
            famc = []
            for c in r.all("FAMC"):
                pedi_raw = c.val("PEDI") or c.val("_FREL") or None
                famc.append((c.value.strip(), PEDI.get((pedi_raw or "").upper()) if pedi_raw else None, pedi_raw))
            death = any(f.tag in ("DEAT", "BURI", "CREM") for f in facts)
            living = "deceased" if death else "unknown"
            linked = {o.value.strip() for o in r.all("OBJE")}
            photo_ptrs = [ph for ph in r.all("_PHOTO") if is_pointer(ph.value) and ph.value.strip() not in linked]
            p = Person(r.xref, stable, names, (r.val("SEX") or "").upper() or None, facts, note_texts(r, "INDI"), cites(r, "INDI"),
                       media_of(r, "person", r.xref, "INDI", photo_ptrs), famc, [c.value.strip() for c in r.all("FAMS")], r, living)
            people[r.xref] = p
        elif r.tag == "FAM":
            if not r.xref:
                warnings.append(f"Line {r.line}: family record without an identifier was skipped.")
                continue
            children = []
            for c in r.all("CHIL"):
                fr, mr = c.val("_FREL"), c.val("_MREL")
                pedi = c.val("PEDI")
                children.append({"xref": c.value.strip(), "raw_frel": fr or pedi, "raw_mrel": mr or pedi,
                                 "frel": PEDI.get((fr or pedi or "").upper()) if (fr or pedi) else None,
                                 "mrel": PEDI.get((mr or pedi or "").upper()) if (mr or pedi) else None})
                for cc in c.children:
                    if cc.tag not in ("_FREL", "_MREL", "PEDI", "NOTE", "SOUR"):
                        unsup(f"FAM.CHIL.{cc.tag}", cc)
            facts = []
            for c in r.children:
                if c.tag in FAM_EVENTS:
                    facts.append(fact(c, FAM_EVENTS, "FAM"))
                elif c.tag.startswith("_") and c.tag not in FAM_KNOWN and (c.first("DATE") or c.first("PLAC")):
                    facts.append(fact(c, FAM_EVENTS, "FAM", custom=True))
                    unsup(f"FAM.{c.tag} (imported as a generic fact)", c)
                elif c.tag not in FAM_KNOWN:
                    unsup(f"FAM.{c.tag}", c)
            for f in facts:
                f.media = media_of(f.node, "family", r.xref, f"FAM.{f.tag}")
            husb = r.val("HUSB")
            wife = r.val("WIFE")
            fam = Family(r.xref, husb.strip() if husb else None, wife.strip() if wife else None, children, facts, note_texts(r, "FAM"),
                         cites(r, "FAM"), media_of(r, "family", r.xref, "FAM"), r,
                         [f"{t}:{clean(c.value)}" for t in ("_UID", "UID", "RIN") for c in r.all(t) if c.value])
            families[r.xref] = fam
        elif r.tag == "SOUR":
            repo_ref = r.first("REPO")
            repo = None
            call_no = clean(r.val("CALN")) or None   # non-standard but seen in Ancestry exports: CALN directly on the source
            if repo_ref is not None:
                repo = repositories.get(repo_ref.value.strip(), {}).get("name") if is_pointer(repo_ref.value) else clean(repo_ref.value) or None
                call_no = clean(repo_ref.val("CALN")) or call_no
            for c in r.children:
                if c.tag not in SOUR_KNOWN:
                    unsup(f"SOUR.{c.tag}", c)
            sources[r.xref] = {"title": clean(r.val("TITL")) or clean(r.val("ABBR")) or "(untitled source)", "author": clean(r.val("AUTH")),
                               "publication": clean(r.val("PUBL")), "abbr": clean(r.val("ABBR")), "text": clean(r.val("TEXT")),
                               "repository": repo, "call_number": call_no, "apid": clean(r.val("_APID")), "www": clean(r.val("WWW")),
                               "notes": note_texts(r, "SOUR"), "media": media_of(r, "source", r.xref, "SOUR"), "node": r}
        elif r.tag in ("NOTE", "REPO", "OBJE", "SUBM", "SUBN", "SNOTE"):
            if r.tag == "SNOTE" and r.xref:
                notes[r.xref] = clean(r.value)
        else:
            unsup(f"{r.tag} (top-level record)", r)

    # Cross-reference checks
    for p in people.values():
        for fx, _, _ in p.famc:
            if fx not in families:
                warnings.append(f"{p.display_name} ({p.xref}) is listed as a child of family {fx}, which is not in the file.")
    for f in families.values():
        for who in [f.husb, f.wife] + [c["xref"] for c in f.children]:
            if who and who not in people:
                warnings.append(f"Family {f.xref} refers to person {who}, who is not in the file.")
    for p in people.values():
        for t in ("_UID", "_MARNM"):
            if p.node.first(t) is not None:
                vendor_mapped[f"INDI.{t} → {'stable identifier' if t == '_UID' else 'married name'}"] += 1
    for f in families.values():
        for c in f.children:
            if c["raw_frel"] or c["raw_mrel"]:
                vendor_mapped["FAM.CHIL._FREL/_MREL → parent relationship type"] += 1
    for c in citations.values():
        if c.node.first("_HPID") is not None or c.node.first("_WPID") is not None:
            vendor_mapped["SOUR._HPID/_WPID → Ancestry person references on a couple citation (kept in the original record)"] += 1
        if c.apid:
            vendor_mapped["SOUR._APID → Ancestry record reference (kept on the source)"] += 1
        if any(x.startswith("http") for x in c.links):
            vendor_mapped["SOUR._LINK / WWW → source web link"] += 1
    for ref in media_refs:
        if not ref["file"] and ref["oid"]:
            vendor_mapped["OBJE with Ancestry media id (RIN) → listed as held on Ancestry, file not in export"] += 1
    for o in objects.values():
        if any(c.tag.startswith("_") and c.tag in OBJE_KNOWN for c in o.children):
            vendor_mapped["OBJE program metadata (_MTYPE, _CREA, _CLON, _CROP …) → kept in the original record"] += 1
    return Model(people, families, sources, repositories, notes, objects, unsupported, examples, vendor_mapped, warnings, media_refs, citations)


def summarize_vendor(m: Model) -> list[dict]:
    return [{"mapping": k, "count": v} for k, v in m.vendor_mapped.most_common()]


def summarize_unsupported(m: Model) -> list[dict]:
    return [{"path": k, "count": v, "example": m.unsupported_examples.get(k)} for k, v in m.unsupported.most_common()]
