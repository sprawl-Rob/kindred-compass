"""Bring a record you found on another site (Ancestry, FamilySearch, American Ancestors, …) into the tree.

The app never reads those sites itself. You copy the record's details from the page you're viewing (or use
the "Clip to Kindred Compass" bookmark button, which sends the page's text to the app), and this module:

1. parse(): reads the "label → value" fields that record pages show (Name, Age, Birth Year, Birthplace,
   Home in 1920 / Event Place, Relation to Head, Spouse, Father, Mother, Immigration Year, Occupation, Death,
   Burial…) and the household table, and works out the record type, year and place;
2. preview(): turns them into facts for the person and people in the household, matching household members
   to relatives already in the tree;
3. save(): creates the source (with a citation and the pasted text as its transcription) and only the facts
   and people you ticked, each linked to the source as evidence.
"""
from __future__ import annotations

import re
from datetime import date

from . import evidence as ev, family as fam, nameequiv, placenorm, workspace as ws
from .db import Tx, one
from .directory import NotFound, ValidationError

# Field labels as record pages write them → our keys
LABELS = [
    (r"^name$|^full name$|^principal$|^name of child$|^child'?s name$|^full name of child$|^name of deceased$|^deceased$|^full name of deceased$"
     r"|^name of person$|^name of the deceased$|^child$", "name"),
    (r"^(name of )?groom$|^bridegroom$|^name of bridegroom$|^groom'?s name$", "groom"),
    (r"^(name of )?bride$|^bride'?s name$|^bride'?s maiden name$", "bride"),
    (r"^(birth ?place|place of birth) of father$|^father'?s place of birth$", "father_birthplace"),
    (r"^(birth ?place|place of birth) of mother$|^mother'?s place of birth$", "mother_birthplace"),
    (r"^name of father$|^full name of father$|^father of child$", "father"),
    (r"^name of mother$|^(full )?maiden name of mother$|^mother of child$", "mother"),
    (r"^cause of death$|^disease or cause of death$", "cause_of_death"),
    (r"^informant$|^name of informant$", "informant"),
    (r"^residence of parents$|^usual residence$|^residence of deceased$|^last residence$", "residence_place"),
    (r"^(place of )?burial or removal$|^place of burial$", "burial_place"),
    (r"^officiant$|^clergyman$|^by whom married$|^person performing (the )?ceremony$", "officiant"),
    (r"^witness(es)?$", "witnesses"),
    (r"^branch( of service)?$|^department,? component and branch.*$|^service branch$|^component$", "branch"),
    (r"^rank$|^grade,? rate,? or rank.*$|^grade$|^pay grade$", "rank"),
    (r"^date entered (active duty|service|ad).*$|^date of entry.*$|^entered service$|^date entered$", "service_entry"),
    (r"^separation date.*$|^date of separation$|^discharge date$|^date discharged$", "service_separation"),
    (r"^character of service.*$|^type of separation$", "service_character"),
    (r"^decorations.*$|^medals.*$", "decorations"),
    (r"^sex$|^gender$", "sex"),
    (r"^age$|^age at death$|^age at event$", "age"),
    (r"^birth( year)?( \(estimated\))?$|^birth date$|^date of birth$|^estimated birth year$|^birth year \(estimated\)$|^born$", "birth_date"),
    (r"^birth ?place$|^place of birth$|^birthplace$", "birth_place"),
    (r"^home in (\d{4})$|^residence( place)?$|^event place$|^residence place$|^home$|^location$|^place$", "residence_place"),
    (r"^residence date$|^event date$|^census date$|^year$|^date$", "event_date"),
    (r"^event type$|^record type$", "event_type"),
    (r"^street( address)?$|^address$", "street"),
    (r"^relation(ship)? to head( of (house|household))?$|^relationship$|^relation$", "relation"),
    (r"^marital status$|^marital condition$", "marital"),
    (r"^spouse('s)? name$|^spouse$|^husband$|^wife$|^spouse full name$", "spouse"),
    (r"^father('s)? name$|^father$|^father full name$", "father"),
    (r"^mother('s)? name$|^mother$|^mother full name$|^mother's maiden name$", "mother"),
    (r"^father('s)? birth ?place$", "father_birthplace"),
    (r"^mother('s)? birth ?place$", "mother_birthplace"),
    (r"^immigration year$|^year of immigration$|^arrival year$|^arrival date$|^immigration$", "immigration"),
    (r"^naturali[sz]ation( year| status)?$|^citizenship$", "naturalization"),
    (r"^occupation$|^occupation \(.*\)$", "occupation"),
    (r"^death date$|^date of death$|^death$|^died$", "death_date"),
    (r"^death place$|^place of death$", "death_place"),
    (r"^burial date$", "burial_date"),
    (r"^burial place$|^cemetery$|^burial$", "burial_place"),
    (r"^marriage date$|^date of marriage$", "marriage_date"),
    (r"^marriage place$|^place of marriage$", "marriage_place"),
    (r"^(native|mother) tongue$|^language$", "language"),
    (r"^household members?.*$|^household$|^household members \(name, age\)$", "_household"),
    (r"^(collection|source|record collection|database)$", "collection"),
]
RELATIONS = {"head", "self", "wife", "husband", "spouse", "son", "daughter", "child", "father", "mother", "brother", "sister", "grandson",
             "granddaughter", "grandchild", "son-in-law", "daughter-in-law", "father-in-law", "mother-in-law", "nephew", "niece", "boarder",
             "lodger", "servant", "stepson", "stepdaughter", "adopted son", "adopted daughter", "cousin", "uncle", "aunt", "brother-in-law",
             "sister-in-law", "roomer", "partner", "inmate", "patient", "employee", "grandfather", "grandmother"}
MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"


def _key(label: str) -> str | None:
    l = re.sub(r"\s+", " ", label.strip().strip(":").lower())
    for pat, key in LABELS:
        if re.match(pat, l):
            return key
    return None


def _years(s: str) -> list:
    return [int(y) for y in re.findall(r"\b(1[5-9]\d\d|20[0-2]\d)\b", s or "")]


def parse(text: str, url: str | None = None, title: str | None = None) -> dict:
    text = (text or "").replace("\r", "")
    if len(text.strip()) < 5:
        raise ValidationError("Paste the record's details (select the record on the page and copy it)")
    lines = [l.rstrip() for l in text.split("\n")]
    fields: dict = {}
    household: list = []
    in_house = False
    home_year = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        # "Label<TAB>Value", "Label: Value", or a label on its own line with the value on the next line
        parts = re.split(r"\t+|\s{3,}", line)
        label, value = None, None
        if len(parts) >= 2 and _key(parts[0]):
            label, value = parts[0], " ".join(parts[1:]).strip()
        elif ":" in line and _key(line.split(":", 1)[0]):
            label, value = line.split(":", 1)[0], line.split(":", 1)[1].strip()
        elif _key(line) and i < len(lines) and lines[i].strip() and not _key(lines[i].strip()):
            label, value = line, lines[i].strip()
            i += 1
        if label:
            k = _key(label)
            if k == "_household":
                in_house = True
                continue
            m = re.match(r"home in (\d{4})", label.strip().lower())
            if m:
                home_year = int(m.group(1))
            in_house = False
            if k and value and k not in fields:
                fields[k] = value
            continue
        if in_house:
            row = _household_row(line)
            if row:
                household.append(row)
            continue
        if line.lower() in ("household", "household members", "name age", "name relationship age") or re.match(r"^household( members)?\b", line, re.I):
            in_house = True
    # FamilySearch-style "Household  Relationship  Sex  Age  Birthplace" header followed by rows
    if not household:
        for j, line in enumerate(lines):
            if re.match(r"^\s*(household|name)\s*[\t ]+\s*(relationship|age)", line, re.I):
                for row_line in lines[j + 1: j + 30]:
                    row = _household_row(row_line.strip())
                    if row:
                        household.append(row)
                    elif row_line.strip() == "":
                        continue
                    else:
                        break
                break
    collection = fields.get("collection") or _guess_collection(text, title)
    kind = fam.classify_source(collection or title or "", url)
    year = (kind.get("year") or home_year or (_years(fields.get("event_date", ""))[:1] or [None])[0]
            or (_years(collection or "")[:1] or [None])[0])
    site = _site(url)
    return {"fields": fields, "household": household, "collection": collection, "kind": kind["kind"], "year": year, "site": site,
            "url": url, "title": title}


def _household_row(line: str) -> dict | None:
    if not line or len(line) > 160:
        return None
    cells = [c.strip() for c in re.split(r"\t+|\s{2,}", line) if c.strip()]
    if not cells or _key(cells[0]):
        return None
    name, rel, age, sex, bp = cells[0], None, None, None, None
    if not re.search(r"[A-Za-z]{2}", name) or name.lower() in ("name", "household"):
        return None
    for c in cells[1:]:
        cl = c.lower()
        if cl in RELATIONS or cl.rstrip(".") in RELATIONS:
            rel = cl.rstrip(".")
        elif re.fullmatch(r"\d{1,3}(\s*\d+/12)?|\d{1,2}m|\d{1,2} months?", cl):
            age = c
        elif cl in ("m", "f", "male", "female"):
            sex = "M" if cl.startswith("m") else "F"
        elif re.search(r"[a-z]{3}", cl):
            bp = bp or c
    # "Oscar Lindqvist 42" pasted as one cell
    if len(cells) == 1:
        m = re.match(r"^(.*?)\s+(\d{1,3})$", name)
        if m:
            name, age = m.group(1), m.group(2)
        else:
            return None
    return {"name": name, "relation": rel, "age": age, "sex": sex, "birth_place": bp}


def _guess_collection(text: str, title: str | None) -> str | None:
    for src in (title or "", text[:600]):
        m = re.search(r"(1[789]\d0 United States Federal Census|United States Census, 1[789]\d0|[A-Z][A-Za-z ,.'&-]{5,80}(Census|Records|Index|Registers?|Lists?|Cards?|Collection),? ?(1[5-9]\d\d(-|–)?(1[5-9]\d\d|20\d\d)?)?)", src)
        if m:
            return m.group(0).strip(" -–|")
    if title:
        return re.sub(r"\s*[-|]\s*(Ancestry(\.com)?|FamilySearch|American Ancestors).*$", "", title).strip() or None
    return None


def _site(url: str | None) -> str | None:
    if not url:
        return None
    for host, name in (("ancestry", "Ancestry"), ("familysearch", "FamilySearch"), ("americanancestors", "American Ancestors"),
                       ("newyorkfamilyhistory", "NYG&B"), ("findagrave", "Find a Grave"), ("myheritage", "MyHeritage"),
                       ("newspapers.com", "Newspapers.com"), ("archives.gov", "National Archives"), ("fold3", "Fold3"),
                       ("genealogybank", "GenealogyBank"), ("billiongraves", "BillionGraves"), ("loc.gov", "Library of Congress")):
        if host in url:
            return name
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else None


# ------------------------------------------------------------------ preview: facts and people

def _fold(s):
    return nameequiv.fold(s or "")


def _first(name: str) -> str:
    t = [x for x in re.split(r"\s+", (name or "").replace('"', "")) if x]
    return _fold(t[0]) if t else ""


def _same_given(a: str, b: str) -> bool:
    fa, fb = _first(a), _first(b)
    if not fa or not fb:
        return False
    if fa == fb:
        return True
    return fb in {_fold(x) for x in nameequiv.given_equivalents(fa)}


def preview(conn, person_id: str, parsed: dict) -> dict:
    p = one(conn, "SELECT project_id, display_name FROM persons WHERE id = ?", (person_id,))
    if not p:
        raise NotFound("person")
    f = fam.load(conn, p["project_id"])
    me = f.people[person_id]
    F = parsed["fields"]
    year = parsed.get("year")
    facts = []

    def fact(key, ctype, date_text, place, value=None, label=None, checked=True):
        if not (date_text or place or value):
            return
        facts.append({"key": key, "claim_type": ctype, "date_text": date_text, "place": place, "value_text": value, "checked": checked,
                      "label": label or ctype})
    event_place = F.get("residence_place")
    kind = parsed.get("kind")
    if kind in ("census", "state_census", "directory") or F.get("residence_place"):
        fact("residence", "residence", str(year) if year else F.get("event_date"), event_place,
             label=f"Lived{' in ' + str(year) if year else ''}" + (f" (street: {F['street']})" if F.get("street") else ""))
    bd = F.get("birth_date")
    if not bd and F.get("age") and year:
        try:
            bd = f"abt {year - int(re.match(r'\\d+', F['age']).group(0))}"
        except (AttributeError, ValueError):
            bd = None
    if bd or F.get("birth_place"):
        fact("birth", "birth", bd if bd and not re.match(r"^\d{4}$", bd or "") or kind not in ("census", "state_census") else f"abt {bd}",
             F.get("birth_place"), label="Born", checked=True)
    if F.get("immigration"):
        y = (_years(F["immigration"])[:1] or [None])[0]
        fact("immigration", "immigration", str(y) if y else F["immigration"], None, label="Arrived in the U.S." if y else "Immigration")
    if F.get("naturalization") and F["naturalization"].lower() not in ("alien", "al", "no"):
        fact("naturalization", "naturalization", F["naturalization"] if _years(F["naturalization"]) else None, None,
             value=None if _years(F["naturalization"]) else F["naturalization"], label="Naturalization")
    if F.get("occupation"):
        fact("occupation", "occupation", str(year) if year else None, None, value=F["occupation"], label="Occupation")
    if F.get("service_entry") or F.get("service_separation") or F.get("branch"):
        span = " – ".join(x for x in [F.get("service_entry"), F.get("service_separation")] if x)
        what = ", ".join(x for x in [F.get("branch"), F.get("rank"), F.get("service_character")] if x)
        fact("military", "military", span or None, None, value=what or None, label="Military service")
    if F.get("marriage_date") or F.get("marriage_place"):
        fact("marriage", "marriage", F.get("marriage_date"), F.get("marriage_place"), label="Married")
    if F.get("death_date") or F.get("death_place"):
        fact("death", "death", F.get("death_date"), F.get("death_place"), label="Died")
    if F.get("burial_date") or F.get("burial_place"):
        fact("burial", "burial", F.get("burial_date"), F.get("burial_place"), label="Buried")

    # people named in the record
    my_rel = (F.get("relation") or "").lower()
    people = []
    named = []
    for row in parsed.get("household") or []:
        if not row.get("relation") and F.get("spouse") and _same_given(row["name"], F["spouse"]):
            row = {**row, "relation": "husband" if (me.sex or "").upper().startswith("F") else "wife"}
        if _same_given(row["name"], me.name) and (not row.get("relation") or row["relation"] in ("head", "self") or row["relation"] == my_rel):
            continue   # that's this person
        named.append(row)
    for key, rel in (("spouse", "spouse"), ("father", "father"), ("mother", "mother")):
        if F.get(key) and not any(_same_given(r["name"], F[key]) for r in named):
            named.append({"name": F[key], "relation": rel, "age": None, "sex": "M" if rel == "father" else "F" if rel == "mother" else None,
                          "birth_place": F.get(f"{rel}_birthplace") if rel in ("father", "mother") else None})
    my_age = int(re.match(r"\d+", F["age"]).group(0)) if F.get("age") and re.match(r"\d+", F["age"]) else None
    my_surnames = {_fold(x) for x in me.surnames + me.married_surnames} | {_fold(f.search_surname(me.id))}
    for row in named:
        rel = _relationship_to_me(my_rel, row.get("relation"))
        inferred = False
        if rel is None and not row.get("relation") and my_age and row.get("age") and re.match(r"\d+", row["age"]) \
                and my_rel in ("head", "self", "") and _fold(row["name"].split()[-1]) in my_surnames:
            if int(re.match(r"\d+", row["age"]).group(0)) <= my_age - 15:
                rel, inferred = "child", True     # same surname, a generation younger, in the head's household
        match, pool_rel = _match_relative(f, me, row, rel)
        if match and not rel:
            rel = pool_rel
        age = row.get("age")
        born = None
        if age and year:
            m = re.match(r"\d+", age)
            if m:
                born = f"abt {year - int(m.group(0))}"
        has_birth = bool(match and f.birth(match["id"]) and not f.birth(match["id"]).get("estimated"))
        people.append({"name": row["name"], "relation_in_record": row.get("relation"), "relationship": rel, "relationship_inferred": inferred,
                       "age": age, "born": None if has_birth else born,
                       "sex": row.get("sex") or _sex_for(row.get("relation")), "birth_place": row.get("birth_place"),
                       "match": match, "action": "link" if match else ("add" if rel in ("spouse", "child", "parent", "sibling") else "skip")})
    title = _source_title(parsed)
    return {"person": {"id": person_id, "name": me.name}, "facts": facts, "people": people, "source": {
        "title": title, "url": parsed.get("url"), "repository": parsed.get("site"), "record_date_text": str(year) if year else None,
        "citation": _citation(parsed, me.name, F)}, "parsed": parsed}


def _sex_for(rel):
    rel = (rel or "").lower()
    if rel in ("wife", "mother", "daughter", "sister", "granddaughter", "stepdaughter", "daughter-in-law", "mother-in-law", "niece", "aunt", "grandmother"):
        return "F"
    if rel in ("husband", "father", "son", "brother", "grandson", "stepson", "son-in-law", "father-in-law", "nephew", "uncle", "grandfather"):
        return "M"
    return None


def _relationship_to_me(my_rel: str, their_rel: str | None) -> str | None:
    """Turn 'relationship to head' into a relationship to this person, where it's unambiguous."""
    r = (their_rel or "").lower()
    me = (my_rel or "head").lower()
    if r in ("father", "mother") and me in ("head", "self", ""):
        return "parent"
    if me in ("head", "self", ""):
        return {"wife": "spouse", "husband": "spouse", "spouse": "spouse", "son": "child", "daughter": "child", "child": "child",
                "stepson": "child", "stepdaughter": "child", "adopted son": "child", "adopted daughter": "child",
                "brother": "sibling", "sister": "sibling"}.get(r)
    if me in ("son", "daughter", "child", "stepson", "stepdaughter"):
        return {"head": "parent", "wife": "parent", "husband": "parent", "son": "sibling", "daughter": "sibling", "child": "sibling"}.get(r)
    if me in ("wife", "husband", "spouse"):
        return {"head": "spouse", "son": "child", "daughter": "child", "child": "child"}.get(r)
    return None


def _match_relative(f, me, row, rel) -> tuple:
    """Find the record's person among this person's relatives. Returns (match, how they're related)."""
    siblings = [s for pa in me.parents for s in f.people[pa].children if s != me.id]
    pools = [("spouse", me.spouses), ("child", me.children), ("parent", me.parents), ("sibling", siblings)]
    if rel:
        pools = [x for x in pools if x[0] == rel]
    for prel, cands in pools:
        for c in dict.fromkeys(cands):
            p = f.people[c]
            if _same_given(row["name"], p.name) or any(_same_given(row["name"], g) for g in p.givens):
                return {"id": c, "name": p.name}, prel
    return None, None


def _source_title(parsed) -> str:
    coll = parsed.get("collection")
    kind, year = parsed.get("kind"), parsed.get("year")
    if kind == "census" and year and (not coll or str(year) not in coll):
        coll = f"{year} United States Federal Census"
    return coll or parsed.get("title") or "Record found online"


def _citation(parsed, name, F) -> str:
    bits = [parsed.get("site"), f"“{_source_title(parsed)},” database" + (" with images" if parsed.get("site") in ("Ancestry", "FamilySearch") else ""),
            f"entry for {F.get('name') or name}" + (f", {F['residence_place']}" if F.get("residence_place") else ""),
            parsed.get("url"), f"accessed {date.today().isoformat()}"]
    return ", ".join(b for b in bits if b) + "."


# ------------------------------------------------------------------ save

def save(conn, person_id: str, body: dict) -> dict:
    p = one(conn, "SELECT project_id, display_name FROM persons WHERE id = ?", (person_id,))
    if not p:
        raise NotFound("person")
    pid = p["project_id"]
    src = body.get("source") or {}
    if not body.get("source_id") and not (src.get("title") or "").strip():
        raise ValidationError("The source needs a title")
    made = {"facts": 0, "people_added": 0, "people_linked": 0}
    with Tx(conn):
        if body.get("source_id"):
            s = one(conn, "SELECT * FROM sources WHERE id = ? AND project_id = ?", (body["source_id"], pid))
            if not s:
                raise NotFound("source")
        else:
            s = ev.create_source(conn, pid, {"title": src["title"][:500], "url": src.get("url"), "repository": src.get("repository"),
                                             "record_date_text": src.get("record_date_text"), "citation_text": src.get("citation"),
                                             "transcription": (body.get("text") or "")[:60000] or None, "accessed_on": date.today().isoformat(),
                                             "record_format": src.get("record_format") or "index",
                                             "provenance_note": f"Captured from {src.get('repository') or 'a website'} by the user on {date.today().isoformat()}.",
                                             "allow_duplicate": True})
        sid = s["id"]
        for fct in body.get("facts") or []:
            if not fct.get("checked"):
                continue
            pl = placenorm.parse(fct.get("place") or "")
            c = ws.create_claim(conn, pid, {"person_id": person_id, "claim_type": fct["claim_type"], "date_text": fct.get("date_text") or "",
                                            "value_text": fct.get("value_text"), "status": "working",
                                            "place": ({"name": fct["place"], "country": pl.country, "region": pl.state, "county": pl.county,
                                                       "municipality": pl.town} if fct.get("place") else None)})
            ev.link_evidence(conn, c["id"], sid, {"stance": "supports", "identity_match": "probable", "assessment": "unassessed"})
            made["facts"] += 1
        for row in body.get("people") or []:
            act = row.get("action")
            rel = row.get("relationship")
            if act == "link" and row.get("match"):
                other = row["match"]["id"]
                # the record mentions this relative: cite it on the relationship
                c = _find_rel(conn, person_id, other, rel)
                if c:
                    ev.link_evidence(conn, c, sid, {"stance": "supports", "identity_match": "probable", "assessment": "unassessed"})
                if row.get("born"):
                    bc = ws.create_claim(conn, pid, {"person_id": other, "claim_type": "birth", "date_text": row["born"], "status": "working",
                                                     "place": _place(row.get("birth_place"))})
                    ev.link_evidence(conn, bc["id"], sid, {"stance": "supports", "identity_match": "probable", "assessment": "unassessed",
                                                           "interpretation_note": f"Age {row.get('age')} in this record"})
                made["people_linked"] += 1
            elif act == "add" and rel in ("spouse", "child", "parent", "sibling"):
                given, surname = _split(row["name"])
                claims = []
                if row.get("born"):
                    claims.append({"claim_type": "birth", "date_text": row["born"], "status": "working", "place": _place(row.get("birth_place"))})
                np_ = ws.create_person(conn, pid, {"names": [{"name_type": "birth", "given": given, "surname": surname}], "sex": row.get("sex"),
                                                   "living_status": "unknown", "claims": claims})
                for c in ws.list_claims(conn, person_id=np_["id"]):
                    ev.link_evidence(conn, c["id"], sid, {"stance": "supports", "identity_match": "probable", "assessment": "unassessed"})
                if rel == "sibling":
                    # siblings share parents; with no parents recorded, note it as a sibling relationship
                    rc = ws.create_claim(conn, pid, {"person_id": np_["id"], "claim_type": "relationship", "relationship_type": "sibling",
                                                     "related_person_id": person_id, "status": "tentative"})
                else:
                    # claim on the new person, read as "<new> is <rel'> of <me>"
                    their = {"spouse": "spouse", "child": "child", "parent": "parent"}[rel]
                    rc = ws.create_claim(conn, pid, {"person_id": np_["id"], "claim_type": "relationship", "relationship_type": their,
                                                     "related_person_id": person_id, "status": "tentative",
                                                     "statement": f"Named in {src['title']} as {row.get('relation_in_record') or rel}"})
                ev.link_evidence(conn, rc["id"], sid, {"stance": "supports", "identity_match": "probable", "assessment": "unassessed"})
                made["people_added"] += 1
    return {"source_id": sid, **made}


def _place(text):
    if not text:
        return None
    pl = placenorm.parse(text)
    return {"name": text, "country": pl.country, "region": pl.state, "county": pl.county, "municipality": pl.town}


def _split(name: str) -> tuple[str, str]:
    t = name.replace('"', "").split()
    if len(t) == 1:
        return "", t[0]
    if "," in name:
        last, first = name.split(",", 1)
        return first.strip(), last.strip()
    return " ".join(t[:-1]), t[-1]


def _find_rel(conn, a, b, rel) -> str | None:
    opposite = {"child": "parent", "parent": "child", "spouse": "spouse", "sibling": "sibling"}
    r = conn.execute("""SELECT id FROM claims WHERE claim_type = 'relationship' AND
                        ((person_id = ? AND related_person_id = ?) OR (person_id = ? AND related_person_id = ?)) LIMIT 1""", (a, b, b, a)).fetchone()
    return r[0] if r else None
