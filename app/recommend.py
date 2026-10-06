"""Deterministic, explainable next-search recommendations.

No LLM is involved. Each recommendation carries the reasons it was ranked, the
coverage that matched (or is unknown), access requirements, how the collection
can be searched, a suggested query, a next action, and its uncertainties.

The rank score orders suggestions by relevance to the research question. It is
NOT a probability that a record exists or that any relationship is correct.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import coverage as cov
from . import directory as d
from . import names as nm
from . import workspace as ws
from .research_log import list_log, search_status
from .taxonomy import ACCESS, CLAIM_TYPES, LOG_OUTCOMES, QUESTION_ANCHORS, QUESTION_TYPES, RECORD_TYPES, SEARCH_CAPABILITIES

PURPOSE = {
    "identify_parents": "investigate possible parents",
    "find_birth": "find a birth or baptism record",
    "find_marriage": "find a marriage record",
    "find_death": "find a death, burial, or estate record",
    "find_origin": "find where they came from",
    "find_immigration": "find their arrival and naturalization",
    "trace_residence": "trace where they lived",
    "find_military": "find military service",
    "find_land": "find land and property records",
    "find_children": "identify the household and children",
    "life_context": "learn about their life and community",
    "other": "learn more about this person",
}

SCORE_NOTE = "Rank points order suggestions by fit to your question. They are not the probability that a record exists or that a relationship is correct."


@dataclass
class Window:
    place: cov.PlaceQuery
    year_from: int | None
    year_to: int | None
    basis: str
    place_label: str = ""


@dataclass
class Prefs:
    access: str | None = None          # None | free | free_or_account | my_access
    subscriptions: list[str] = field(default_factory=list)  # provider ids
    remote_only: bool = False
    languages: list[str] = field(default_factory=list)
    record_types: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, p: dict | None) -> "Prefs":
        p = p or {}
        return cls(p.get("access"), list(p.get("subscriptions") or []), bool(p.get("remote_only")),
                   list(p.get("languages") or []), list(p.get("record_types") or []))


def _place_from(prefix_obj: dict, prefix: str = "place_") -> cov.PlaceQuery:
    return cov.PlaceQuery(prefix_obj.get(prefix + "country"), prefix_obj.get(prefix + "region"), prefix_obj.get(prefix + "county"),
                          prefix_obj.get(prefix + "municipality"), prefix_obj.get(prefix + "historical_jurisdiction"))


def _shift(qtype: str, yf: int | None, yt: int | None, anchor_type: str) -> tuple[int | None, int | None]:
    """Turn an anchor event's years into the years when useful records were likely created."""
    if yf is None and yt is None:
        return None, None
    yf = yf if yf is not None else yt
    yt = yt if yt is not None else yf
    if qtype == "identify_parents" and anchor_type in ("birth", "baptism"):
        return yf - 1, yt + 45  # parents' censuses, deeds, and estates follow the child's birth
    if qtype == "find_marriage" and anchor_type == "birth":
        return yf + 16, yt + 40
    if qtype == "find_death" and anchor_type == "residence":
        return yt, yt + 30
    if qtype == "find_children" and anchor_type == "marriage":
        return yf, yt + 25
    if qtype in ("find_immigration", "find_origin") and anchor_type in ("residence", "birth"):
        return yf - (0 if anchor_type == "birth" else 10), yt + (60 if anchor_type == "birth" else 5)
    return yf - 1, yt + 1


def research_windows(person: dict | None, question: dict | None) -> list[Window]:
    qtype = (question or {}).get("question_type") or "other"
    out: list[Window] = []
    if question and (question.get("place_id") or question.get("year_from") or question.get("year_to")):
        out.append(Window(_place_from(question), question.get("year_from"), question.get("year_to"),
                          "Place and years stated in your research question", question.get("place_label") or ""))
    if person:
        anchors = QUESTION_ANCHORS.get(qtype, QUESTION_ANCHORS["other"])
        claims = [c for c in person.get("claims") or [] if c["status"] != "rejected"]
        for atype in anchors:
            for c in claims:
                if c["claim_type"] != atype:
                    continue
                yf, yt = _shift(qtype, c.get("year_from"), c.get("year_to"), atype)
                place = _place_from(c)
                if place.is_empty() and yf is None:
                    continue
                out.append(Window(place, yf, yt, f"{CLAIM_TYPES[atype]} claim: {c.get('date_text') or 'date unknown'}"
                                                 f"{' in ' + c['place_label'] if c.get('place_label') else ''}",
                                  c.get("place_label") or ""))
        # Fall back to any dated/placed claim so useful research can start without a full profile.
        if not out:
            for c in claims:
                place = _place_from(c)
                if not place.is_empty() or c.get("year_from"):
                    out.append(Window(place, c.get("year_from"), c.get("year_to"),
                                      f"{CLAIM_TYPES.get(c['claim_type'], c['claim_type'])} claim", c.get("place_label") or ""))
    # De-duplicate identical windows.
    uniq, seen = [], set()
    for w in out:
        k = (w.place.country, w.place.region, w.place.county, w.place.municipality, w.place.historical_jurisdiction, w.year_from, w.year_to)
        if k not in seen:
            seen.add(k)
            uniq.append(w)
    return uniq


def _years_label(yf, yt) -> str:
    if yf is None and yt is None:
        return "any years"
    if yf == yt:
        return str(yf)
    return f"{yf if yf is not None else '…'}–{yt if yt is not None else '…'}"


def _access_summary(c: dict) -> dict:
    def lab(xs):
        return " or ".join(ACCESS.get(x, x) for x in xs or ["unknown"])
    return {"search": lab(c.get("access_search")), "images": lab(c.get("access_images")), "copies": lab(c.get("access_copies")),
            "notes": c.get("access_notes")}


def _how_to_search(c: dict) -> list[str]:
    caps = c.get("capabilities") or []
    return [SEARCH_CAPABILITIES[x] for x in caps if x in SEARCH_CAPABILITIES] or ["Search method not recorded"]


def suggested_query(person: dict | None, window: Window | None, log_entries: list[dict]) -> dict:
    if not person:
        return {"text": "", "given": [], "surname": [], "variants": [], "years": "", "place": ""}
    tried = []
    for e in log_entries:
        if e.get("person_id") == person["id"]:
            tried += e.get("name_variants") or []
            tried.append(e.get("query_text") or "")
    names = nm.person_name_set(person)
    sug = nm.suggest_for_person(person, tried)
    variants = []
    for g in sug["groups"]:
        if g.get("kind") == "code":
            continue
        for v in g["variants"]:
            if v not in variants and v not in g["tried"]:
                variants.append(v)
    given = names["given"][:1]
    surname = names["surname"][:1]
    years = _years_label(window.year_from, window.year_to) if window else ""
    place = window.place_label if window else ""
    main = " ".join(given + surname) or person.get("display_name", "")
    text = " ".join(x for x in [f"“{main}”" if main else "", years if years != "any years" else "", place] if x)
    return {"text": text, "given": names["given"], "surname": names["surname"], "variants": variants[:8], "years": years, "place": place}


def next_action(c: dict, window: Window | None, has_template: bool) -> dict:
    caps = set(c.get("capabilities") or [])
    years = _years_label(window.year_from, window.year_to) if window else ""
    place = (window.place_label if window else "") or "the relevant place"
    if c.get("adapter_key"):
        return {"kind": "live_search", "label": "Run live search in this app",
                "detail": "Queries the provider's documented public API from this app and shows matching items with links."}
    if has_template:
        return {"kind": "open_prefilled", "label": "Open provider search (pre-filled)",
                "detail": "Opens the provider's site with your query filled in — check the results there."}
    if "name_index" in caps:
        return {"kind": "open_search", "label": "Open provider search", "detail": "Search by name; copy the suggested query and variants."}
    if "full_text" in caps:
        return {"kind": "open_search", "label": "Open provider search", "detail": "Search the full text for the name with the place; try variants and misreadings."}
    if "browse_images" in caps:
        return {"kind": "browse", "label": "Open provider site to browse images",
                "detail": f"No name index — browse the images for {place}, {years}."}
    if "catalog" in caps:
        return {"kind": "catalog", "label": "Open catalog search", "detail": f"Search the catalog by place ({place}) and record type, then open matching items."}
    if caps & {"onsite", "request_only"}:
        return {"kind": "contact", "label": "Open repository website",
                "detail": "Check how to request a search or plan a visit — material may not be online."}
    return {"kind": "open_site", "label": "Open provider site", "detail": "Search method not recorded — check the provider's site."}


def recommend(conn, project_id: str, person_id: str | None = None, question_id: str | None = None,
              prefs: dict | None = None, limit: int = 25) -> dict:
    p = Prefs.from_dict(prefs)
    question = ws.get_question(conn, question_id) if question_id else None
    if question and not person_id:
        person_id = question.get("person_id")
    person = ws.get_person(conn, person_id) if person_id else None
    qtype = (question or {}).get("question_type") or "other"
    desired = list(QUESTION_TYPES.get(qtype, QUESTION_TYPES["other"])["record_types"])
    if p.record_types:
        desired = [r for r in desired if r in p.record_types] + [r for r in p.record_types if r not in desired]

    windows = research_windows(person, question)
    log = list_log(conn, project_id)
    person_log = [e for e in log if not person_id or e.get("person_id") == person_id]
    collections = d.all_collections(conn)
    by_id = {c["id"]: c for c in collections}
    relations = conn.execute("SELECT a_id, b_id, relation, note FROM collection_relations").fetchall()

    recs, guidance, hidden, already = [], [], [], []
    for c in collections:
        rec = _score(c, windows, desired, qtype, person, person_log, relations, by_id, p)
        if rec is None:
            continue
        if c["entry_kind"] in ("guide", "directory"):
            guidance.append(rec)
            continue
        reason = d.access_excluded(c, {"access": p.access, "subscriptions": p.subscriptions, "remote_only": p.remote_only})
        if reason:
            rec["hidden_reason"] = reason
            hidden.append(rec)
            continue
        if rec["search_status"]["state"] in ("found", "searched_no_result", "possible_match"):
            already.append(rec)
            continue
        recs.append(rec)

    key = lambda r: (-r["rank_points"], r["collection"]["name"])
    recs.sort(key=key)
    guidance.sort(key=key)
    hidden.sort(key=key)
    already.sort(key=key)
    return {
        "person": person and {"id": person["id"], "display_name": person["display_name"], "is_private": person["is_private"],
                              "living_status": person["living_status"]},
        "question": question,
        "question_type": qtype,
        "purpose": PURPOSE.get(qtype, PURPOSE["other"]),
        "windows": [{"place": w.place_label or w.place.label(), "years": _years_label(w.year_from, w.year_to), "basis": w.basis} for w in windows],
        "record_types_considered": [{"key": r, "label": RECORD_TYPES.get(r, r)} for r in desired],
        "recommendations": recs[:limit],
        "more_available": max(0, len(recs) - limit),
        "guidance": guidance[:8],
        "already_searched": already,
        "hidden_by_preferences": hidden,
        "alternatives": alternatives_for_person(conn, project_id, person, person_log, windows, by_id) if person else [],
        "score_note": SCORE_NOTE,
        "warnings": _warnings(person, windows),
    }


def _warnings(person, windows) -> list[str]:
    w = []
    if person is None:
        w.append("No person selected — results are based on the question only.")
    if not windows:
        w.append("No places or dates are recorded yet, so geography and dates could not narrow these results. "
                 "Add an approximate date and place to the person or the question.")
    return w


def _score(c, windows, desired, qtype, person, person_log, relations, by_id, p: Prefs) -> dict | None:
    reasons, uncertainty = [], []
    # --- coverage against the best window
    best = None
    for w in windows or [Window(cov.PlaceQuery(), None, None, "No place or dates recorded")]:
        gs, gwhy = cov.geo_match(c["geo_scope"], c["geo"] or [], w.place)
        ds, dwhy = cov.date_match(c["dates"] or [], w.year_from, w.year_to, c["date_gaps"])
        overall = cov.combine(gs, ds)
        if overall == cov.NONE:
            continue
        pts = {cov.MATCH: 30, cov.PARTIAL: 18, cov.UNKNOWN: 8}[gs] + {cov.MATCH: 25, cov.PARTIAL: 15, cov.UNKNOWN: 6}[ds]
        local = gs == cov.MATCH and any(g.get("county") or g.get("municipality") for g in c["geo"] or [])
        if local:
            pts += 8
        cand = (pts, w, gs, gwhy, ds, dwhy, local)
        if best is None or cand[0] > best[0]:
            best = cand
    if best is None:
        return None
    pts, w, gs, gwhy, ds, dwhy, local = best

    # --- record types
    crt = c["record_types"] or []
    matched = [r for r in desired if r in crt]
    is_guide = c["entry_kind"] in ("guide", "directory", "catalog")
    if crt and not matched and not is_guide:
        return None
    if matched:
        pos = desired.index(matched[0])
        pts += max(6, 26 - 2 * pos) + min(8, 2 * (len(matched) - 1))
        reasons.append("Contains " + ", ".join(RECORD_TYPES[r].lower() for r in matched[:4]) +
                       (" — the record types most likely to answer this question" if pos < 3 else ""))
    elif not crt:
        uncertainty.append("Record types in this collection are not recorded in the directory.")
    elif is_guide:
        reasons.append("Research guidance / catalog for this place — useful for finding record sets that are not name-indexed")

    if gs == cov.MATCH:
        reasons.append(gwhy + (f" ({w.place_label})" if w.place_label and w.place_label not in gwhy else ""))
        if local:
            reasons.append("Local repository for this exact area — may hold records that are not online elsewhere")
    elif gs == cov.PARTIAL:
        reasons.append(gwhy)
        uncertainty.append("Only part of the place matches, or coverage is not itemised by place.")
    elif gs == cov.UNKNOWN:
        uncertainty.append("Geographic coverage is not recorded — this may or may not include your place.")
    if ds == cov.MATCH and w.year_from is not None:
        reasons.append(dwhy + f" (you need {_years_label(w.year_from, w.year_to)})")
    elif ds == cov.PARTIAL:
        reasons.append(dwhy)
        uncertainty.append("Date coverage only partly overlaps the years you need.")
    elif ds == cov.UNKNOWN and w.year_from is not None:
        uncertainty.append("Date coverage is not recorded — the years you need may or may not be included.")

    # --- how it can be searched
    caps = set(c["capabilities"] or [])
    if "name_index" in caps:
        pts += 8
    if "full_text" in caps:
        pts += 6 + (4 if qtype in ("find_death", "life_context", "find_origin", "identify_parents") else 0)
    if "browse_images" in caps and not caps & {"name_index", "full_text"}:
        pts += 2
    if "catalog" in caps:
        pts += 2
    if caps and caps <= {"onsite", "request_only"}:
        uncertainty.append("Material may only be available onsite or by request.")

    # --- access
    s = set(c["access_search"] or [])
    if "free" in s:
        pts += 8
    elif "free_account" in s:
        pts += 6
    elif "subscription" in s:
        pts += 6 if c["provider_id"] in p.subscriptions else -4
    if s == {"unknown"} or not s:
        uncertainty.append("Access conditions are not recorded.")
    if c["verification_status"] in ("needs_verification", "broken"):
        pts -= 3
        uncertainty.append("Directory details for this entry have not been verified" if c["verification_status"] == "needs_verification"
                           else "The link for this entry had a problem when last checked")

    # --- search history
    status = search_status(person_log, c["id"])
    hist_note = None
    if status["state"] == "searched_no_result":
        pts -= 25
        hist_note = (f"You searched this on {status['last_searched']} with no result. A failed index search does not mean the record does not exist "
                     "— see alternative steps below.")
    elif status["state"] == "found":
        pts -= 30
        hist_note = f"You already found something here on {status['last_searched']}."
    elif status["state"] == "possible_match":
        pts -= 15
        hist_note = f"You logged a possible match here on {status['last_searched']} — follow up to confirm identity."
    elif status["state"] == "inaccessible":
        pts -= 8
        hist_note = f"You couldn't access this on {status['last_searched']} — check library access or the provider's terms."
    elif status["state"] == "records_unavailable":
        pts -= 30
        hist_note = "You logged these records as unavailable — look for substitute record types."

    # --- overlap with collections already searched
    overlap_notes = []
    for r in relations:
        other = r["b_id"] if r["a_id"] == c["id"] else r["a_id"] if r["b_id"] == c["id"] else None
        if not other or other not in by_id:
            continue
        ost = search_status(person_log, other)
        if ost["state"] != "not_searched":
            overlap_notes.append(f"Overlaps with {by_id[other]['name']} ({by_id[other]['provider_name']}), which you searched on "
                                 f"{ost['last_searched']} ({LOG_OUTCOMES.get(_outcome_of(ost), '')}). "
                                 f"Indexes differ between providers, so a second search can still help." + (f" Note: {r['note']}" if r["note"] else ""))
            pts -= 5

    if c.get("limitations"):
        uncertainty.append(c["limitations"])

    has_template = bool(c.get("search_link_verified") and c.get("search_url_template"))
    sq = suggested_query(person, w if windows else None, person_log)
    action = next_action(c, w if windows else None, has_template)
    years_lab = _years_label(w.year_from, w.year_to) if windows else ""
    purpose = PURPOSE.get(qtype, PURPOSE["other"])
    headline = f"Search {c['name']}" + (f" for {years_lab}" if years_lab and years_lab != "any years" else "") + f" to {purpose}."
    cov_sentence = _coverage_sentence(c, gs, ds, w, caps, s)

    return {
        "collection": {"id": c["id"], "name": c["name"], "provider_name": c["provider_name"], "url": c["url"], "search_url": c["search_url"],
                       "entry_kind": c["entry_kind"], "repository_type": c["repository_type"], "badges": c["badges"],
                       "adapter_key": c.get("adapter_key"), "search_link_verified": bool(c.get("search_link_verified")),
                       "search_url_template": c.get("search_url_template") if has_template else None,
                       "verification_status": c["verification_status"], "last_verified": c["last_verified"]},
        "headline": headline,
        "coverage_sentence": cov_sentence,
        "question_it_may_answer": _question_it_answers(qtype, matched, person),
        "why": reasons,
        "coverage": {"geo": gs, "geo_why": gwhy, "dates": ds, "dates_why": dwhy, "window": {"place": w.place_label, "years": years_lab, "basis": w.basis}},
        "access": _access_summary(c),
        "search_methods": _how_to_search(c),
        "suggested_query": sq,
        "next_action": action,
        "uncertainty": uncertainty,
        "history_note": hist_note,
        "overlap_notes": overlap_notes,
        "search_status": status,
        "rank_points": pts,
    }


def _outcome_of(status: dict) -> str:
    return {"searched_no_result": "no_result", "found": "useful", "possible_match": "possible_match", "inaccessible": "inaccessible",
            "records_unavailable": "records_unavailable", "follow_up": "follow_up"}.get(status["state"], "")


def _coverage_sentence(c, gs, ds, w: Window, caps: set, s: set) -> str:
    where = w.place_label or "this place"
    if gs == cov.MATCH and ds == cov.MATCH:
        main = f"The collection covers {where} and the years you need"
    elif gs == cov.MATCH:
        main = f"The collection covers {where}" + (" (date coverage not recorded)" if ds == cov.UNKNOWN else " for part of the years you need")
    elif gs == cov.PARTIAL:
        main = "The collection covers part of the area you need"
    else:
        main = "The directory does not record whether this collection covers your place"
    caveats = []
    if "browse_images" in caps and not caps & {"name_index", "full_text"}:
        caveats.append("requires browsing images")
    elif caps and caps <= {"onsite", "request_only"}:
        caveats.append("may require an onsite visit or a request")
    if s and s <= {"subscription"}:
        caveats.append("requires a subscription to search")
    elif "free_account" in s and "free" not in s:
        caveats.append("requires a free account")
    return main + (", but " + " and ".join(caveats) if caveats else "") + "."


def _question_it_answers(qtype, matched, person) -> str:
    who = person["display_name"] if person else "this person"
    m = {
        "identify_parents": f"Who were {who}'s parents? Estates, wills, and household records often name children and heirs.",
        "find_birth": f"When and where was {who} born?",
        "find_marriage": f"When, where, and to whom was {who} married?",
        "find_death": f"When and where did {who} die, and who survived them?",
        "find_origin": f"Where did {who} come from before arriving here?",
        "find_immigration": f"When did {who} arrive, and did they naturalize?",
        "trace_residence": f"Where was {who} living, and when did they move?",
        "find_military": f"Did {who} serve, and in which unit?",
        "find_land": f"What land did {who} own, buy, or sell?",
        "find_children": f"Who lived in {who}'s household?",
        "life_context": f"What was {who}'s community and daily life like?",
    }
    return m.get(qtype, f"What more can be learned about {who}?")


# ---------------------------------------------------------------- alternatives after a negative search

def alternatives_for_person(conn, project_id, person, person_log, windows, by_id) -> list[dict]:
    out = []
    for e in person_log:
        if e["outcome"] in ("no_result", "records_unavailable", "inaccessible"):
            out.append({"entry_id": e["id"], "searched": e.get("collection_name") or e.get("resource_text"),
                        "searched_on": e["searched_on"], "outcome": e["outcome"], "outcome_label": LOG_OUTCOMES[e["outcome"]],
                        "suggestions": alternatives_for_entry(conn, e, person, windows, by_id)})
    return out


def alternatives_for_entry(conn, entry: dict, person: dict | None, windows: list[Window], by_id: dict) -> list[dict]:
    sug: list[dict] = []
    c = by_id.get(entry.get("collection_id")) if entry.get("collection_id") else None
    caps = set((c or {}).get("capabilities") or [])
    outcome = entry["outcome"]

    if outcome == "inaccessible" and c:
        lib = "library" in set(c.get("access_search") or []) | set(c.get("access_images") or [])
        sug.append({"kind": "access", "title": "Find another way to access this collection",
                    "reason": ("Some libraries and FamilySearch centers provide free access to subscription or restricted collections. "
                               if lib else "") + "Check whether the same records are indexed by another provider (see related collections).",
                    "action": "Check access options", "collection_id": c["id"]})

    if outcome == "no_result" and person:
        tried = list(entry.get("name_variants") or []) + [entry.get("query_text") or ""]
        groups = nm.suggest_for_person(person, tried)["groups"]
        untried = []
        for g in groups:
            if g.get("kind") == "code":
                continue
            untried += [v for v in g["variants"] if v not in g["tried"] and v not in untried]
        if untried:
            sug.append({"kind": "spelling", "title": "Search again with spelling variants",
                        "reason": "Indexers transcribe names as they read them; clerks spelled names by ear. A miss on one spelling is common.",
                        "action": "Try: " + ", ".join(untried[:6]), "variants": untried[:10],
                        "collection_id": entry.get("collection_id")})

        if entry.get("year_from") is not None or entry.get("year_to") is not None:
            yf, yt = entry.get("year_from"), entry.get("year_to")
            sug.append({"kind": "dates", "title": "Widen the date range",
                        "reason": "Ages and dates in records are often off by several years, and recording could lag the event.",
                        "action": f"Search {_years_label((yf or yt) - 5, (yt or yf) + 5)} instead of {_years_label(yf, yt)}",
                        "collection_id": entry.get("collection_id")})

        rels = [r for r in person.get("relationships") or [] if r.get("related_person_name")]
        if rels:
            names = ", ".join(sorted({r["related_person_name"] for r in rels})[:3])
            sug.append({"kind": "related_people", "title": "Search for related people instead",
                        "reason": "Households were often recorded under the head of household, and relatives appear in each other's records "
                                  "(witnesses, sponsors, heirs).",
                        "action": f"Search for {names} in the same collection and years", "collection_id": entry.get("collection_id")})

    # Full-text search if the failed search was index-based
    if outcome == "no_result" and ("name_index" in caps or not caps):
        for fc in _collections_with(by_id, windows, lambda x: "full_text" in (x.get("capabilities") or []) and x["id"] != entry.get("collection_id"))[:3]:
            sug.append({"kind": "full_text", "title": f"Try a full-text search: {fc['name']}",
                        "reason": "Name indexes only cover the fields that were indexed. Full-text search can find a name inside deeds, wills, "
                                  "and newspaper pages that were never name-indexed (OCR and handwriting recognition can misread names, so try variants).",
                        "action": "Open provider search", "collection_id": fc["id"]})

    # Catalog browsing for unindexed images
    for cc in _collections_with(by_id, windows, lambda x: {"catalog", "browse_images"} <= set(x.get("capabilities") or []) and x["entry_kind"] == "catalog")[:2]:
        sug.append({"kind": "catalog", "title": f"Browse unindexed images via {cc['name']}",
                    "reason": "Many digitized records are browse-only: they are online as images but not searchable by name. The catalog lists "
                              "them by place and record type.",
                    "action": "Search the catalog by place" + (f" ({windows[0].place_label})" if windows and windows[0].place_label else ""),
                    "collection_id": cc["id"]})

    # Local repositories in the same county/state
    local = _collections_with(by_id, windows, lambda x: x["entry_kind"] == "repository" and any(
        g.get("region") or g.get("county") for g in x.get("geo") or []), strict=True)
    for lc in local[:3]:
        sug.append({"kind": "local", "title": f"Ask a local repository: {lc['name']}",
                    "reason": "Original registers, court files, and deeds are often held locally and may never have been put online.",
                    "action": "Open repository website", "collection_id": lc["id"]})

    # Historical jurisdiction
    for w in windows[:2]:
        if w.place.historical_jurisdiction:
            sug.append({"kind": "jurisdiction", "title": f"Search under the historical jurisdiction: {w.place.historical_jurisdiction}",
                        "reason": "Boundaries changed. Records usually stay with the jurisdiction that existed when they were created.",
                        "action": "Repeat the search using the historical place name"})
            break

    if outcome == "records_unavailable":
        sug.append({"kind": "substitute", "title": "Look for substitute record types",
                    "reason": "When a record set was lost or never created, other records often cover the same facts — e.g. tax lists or "
                              "directories for a missing census, church registers for missing civil births, probate for missing deaths.",
                    "action": "Review the other record types suggested for this question"})
    return sug


def _collections_with(by_id: dict, windows: list[Window], pred, strict: bool = False) -> list[dict]:
    out = []
    for c in by_id.values():
        if not pred(c):
            continue
        ok = not windows
        for w in windows:
            gs, _ = cov.geo_match(c["geo_scope"], c["geo"] or [], w.place)
            ds, _ = cov.date_match(c["dates"] or [], w.year_from, w.year_to, c["date_gaps"])
            if strict:
                if gs == cov.MATCH and ds != cov.NONE:
                    ok = True
            elif gs in (cov.MATCH, cov.PARTIAL) and ds != cov.NONE:
                ok = True  # unknown date coverage is not evidence of absence
        if ok:
            out.append(c)
    out.sort(key=lambda c: (c["verification_status"] != "verified", c["name"]))
    return out
