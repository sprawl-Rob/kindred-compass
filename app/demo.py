"""Fictional demonstration project.

Everything here is invented to show how the app works. The people, records,
transcriptions and citations are FICTIONAL; they deliberately carry no URLs to real
records. Directory resources referenced are real entries from the seed directory.
"""
from __future__ import annotations

from . import evidence as ev
from . import research_log as rl
from . import workspace as ws
from .db import Tx, now_iso, one

DEMO_NAME = "Demo: The Whitcomb–Fehrs family (fictional)"
FICTION = "FICTIONAL DEMO RECORD — invented for demonstration; not a real document."


def ensure_demo(conn) -> str | None:
    state = one(conn, "SELECT * FROM seed_state WHERE name = 'demo'")
    if state:
        return None  # created once; the user may have deleted it on purpose
    pid = create_demo(conn)
    conn.execute("INSERT INTO seed_state (name, version, applied_at) VALUES ('demo', 1, ?)", (now_iso(),))
    return pid


def reset_demo(conn) -> dict:
    with Tx(conn):
        for r in conn.execute("SELECT id FROM projects WHERE is_demo = 1").fetchall():
            conn.execute("DELETE FROM projects WHERE id = ?", (r["id"],))
    return {"project_id": create_demo(conn)}


def _coll(conn, seed_key):
    r = one(conn, "SELECT id FROM collections WHERE seed_key = ?", (seed_key,))
    return r["id"] if r else None


def create_demo(conn) -> str:
    with Tx(conn):
        p = ws.create_project(conn, {"name": DEMO_NAME, "is_demo": True,
                                     "description": "A fictional family used to demonstrate the workflow. Nothing in this project is real. "
                                                    "Delete it or reset it any time from Settings."})
        pid = p["id"]
        worcester = {"country": "United States", "region": "Massachusetts", "county": "Worcester", "municipality": "Fitchburg",
                     "name": "Fitchburg, Worcester County, Massachusetts"}
        holstein = {"country": "Germany", "region": "Schleswig-Holstein", "historical_jurisdiction": "Duchy of Holstein (Prussia from 1867)",
                    "name": "Holstein (now Schleswig-Holstein, Germany)"}

        josiah = ws.create_person(conn, pid, {
            "display_name": "Josiah Whitcomb", "living_status": "deceased",
            "notes": "Fictional demo person. Goal: identify his parents.",
            "names": [{"name_type": "birth", "given": "Josiah", "surname": "Whitcomb"},
                      {"name_type": "variant", "given": "Josiah", "surname": "Whitcombe", "note": "Spelling seen in the (fictional) 1880 census"}],
            "claims": [
                {"claim_type": "birth", "date_text": "abt 1852", "place": worcester, "statement": "Age 28 in the 1880 census (fictional)", "status": "tentative"},
                {"claim_type": "birth", "date_text": "1849", "place": {"country": "United States", "region": "New Hampshire", "name": "New Hampshire"},
                 "statement": "Death record (fictional) gives birth 1849 in New Hampshire", "status": "tentative"},
                {"claim_type": "residence", "date_text": "1880", "place": worcester, "statement": "Household head in 1880 (fictional)", "status": "working"},
                {"claim_type": "death", "date_text": "12 Mar 1903", "place": worcester, "status": "working"},
            ]})
        margarethe = ws.create_person(conn, pid, {
            "display_name": "Margarethe (Fehrs) Whitcomb", "living_status": "deceased",
            "notes": "Fictional demo person. Goal: find her place of origin.",
            "names": [{"name_type": "maiden", "given": "Margarethe", "surname": "Fehrs"},
                      {"name_type": "married", "given": "Margaret", "surname": "Whitcomb"},
                      {"name_type": "variant", "given": "Margaretha", "surname": "Fehrs"}],
            "claims": [
                {"claim_type": "birth", "date_text": "abt 1855", "place": holstein, "status": "working"},
                {"claim_type": "immigration", "date_text": "bet 1866 and 1872", "place": {"country": "United States", "region": "New York", "name": "New York"},
                 "status": "working", "statement": "Family story: arrived as a teenager"},
                {"claim_type": "residence", "date_text": "1880", "place": worcester, "status": "working"},
            ]})
        ws.create_claim(conn, pid, {"person_id": margarethe["id"], "claim_type": "relationship", "relationship_type": "spouse",
                                    "related_person_id": josiah["id"], "date_text": "abt 1875", "status": "tentative",
                                    "statement": "Listed as wife in the 1880 census (fictional)"})

        q1 = ws.create_question(conn, pid, {"person_id": josiah["id"], "question_type": "identify_parents",
                                            "question": "Who were Josiah Whitcomb's parents?",
                                            "notes": "Two different birth places are claimed (Massachusetts vs New Hampshire)."})
        ws.create_question(conn, pid, {"person_id": margarethe["id"], "question_type": "find_origin",
                                       "question": "Where in Holstein did Margarethe Fehrs come from?"})

        fs = _coll(conn, "familysearch-historical-records")
        rl.create_entry(conn, pid, {"person_id": josiah["id"], "question_id": q1["id"], "collection_id": fs,
                                    "resource_text": None if fs else "FamilySearch Historical Records",
                                    "query_text": "Josiah Whitcomb, born 1850–1854, Massachusetts", "name_variants": ["Josiah Whitcomb"],
                                    "year_from": 1850, "year_to": 1854, "place_text": "Massachusetts", "searched_on": "2026-09-20",
                                    "outcome": "no_result", "notes": "Demo entry: no indexed birth found. This does not mean no record exists."})

        census = ev.create_source(conn, pid, {
            "title": "1880 census entry, Josiah Whitcombe household (FICTIONAL)", "repository": "Demo repository (fictional)",
            "record_date_text": "1880", "page_ref": "Sheet 12, line 4 (fictional)", "record_format": "transcription",
            "informant": "Unknown household member", "informant_knowledge": "undetermined",
            "transcription": "Whitcombe, Josiah — head — 28 — b. Mass. — machinist\nWhitcombe, Margaret — wife — 25 — b. Prussia",
            "provenance_note": FICTION})
        death = ev.create_source(conn, pid, {
            "title": "Death register entry for Josiah Whitcomb, 1903 (FICTIONAL)", "repository": "Demo town clerk (fictional)",
            "record_date_text": "12 Mar 1903", "page_ref": "Entry 77 (fictional)", "record_format": "original_image",
            "informant": "Son, George Whitcomb", "informant_knowledge": "secondary",
            "transcription": "Josiah Whitcomb, age 53y 10m, born New Hampshire, father: Amos Whitcomb, mother: Lydia —",
            "provenance_note": FICTION})
        tree = ev.create_source(conn, pid, {
            "title": "Online family tree naming Josiah's parents (FICTIONAL)", "record_format": "contributed_tree",
            "transcription": "Josiah Whitcomb b. 1852 Fitchburg, son of Amos Whitcomb and Lydia Gates",
            "provenance_note": FICTION + " Contributed trees are clues, not proof."})

        jc = {c["claim_type"] + (c.get("date_text") or ""): c["id"] for c in ws.list_claims(conn, person_id=josiah["id"])}
        ev.link_evidence(conn, jc["birthabt 1852"], census["id"], {"stance": "supports", "identity_match": "probable", "assessment": "moderate",
                                                                  "interpretation_note": "Age 28 in 1880 implies birth about 1851–1852."})
        ev.link_evidence(conn, jc["birth1849"], death["id"], {"stance": "supports", "identity_match": "probable", "assessment": "weak",
                                                             "interpretation_note": "Informant was a son reporting secondhand."})
        ev.link_evidence(conn, jc["birthabt 1852"], death["id"], {"stance": "contradicts", "identity_match": "probable", "assessment": "weak",
                                                                 "interpretation_note": "Death record gives New Hampshire and ~1849."})
        ev.link_evidence(conn, jc["birthabt 1852"], tree["id"], {"stance": "supports", "identity_match": "possible", "assessment": "weak",
                                                                "interpretation_note": "Tree cites no sources."})
        ws.create_task(conn, pid, {"title": "Search Worcester County probate for an Amos Whitcomb estate, 1870–1900", "person_id": josiah["id"],
                                   "question_id": q1["id"], "notes": "Demo task."})
    return pid
