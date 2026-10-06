"""Combine two family trees (projects) into one — e.g. a father's tree and a mother's tree.

1. suggest(): find people who appear in both trees. Names are compared the way records write them (nicknames,
   quoted "went by" names, middle names, spelling variants, married names); dates, birthplaces and sex must not
   conflict; matching relatives (parents, spouses, children) raise confidence. Suggestions are only suggestions —
   nothing is merged until the user confirms each pair.
2. combine(): copy everything from the source tree into the target tree (people, names, places, facts, sources,
   evidence links, questions, tasks, research log, attachments). Each confirmed pair becomes one person: the
   source person's facts, names and relationships are added to the target person; facts that are exactly the
   same are not duplicated (their sources are combined). The source tree itself is left unchanged.
3. undo(): remove everything the combine added.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import family as fam, nameequiv
from .db import Tx, insert, new_id, now_iso, one, rows, update
from .directory import NotFound, ValidationError

HIGH, POSSIBLE, CONFLICT = "high", "possible", "conflict"   # conflict: same name and family, but a date disagrees


# ------------------------------------------------------------------ matching

def _fold(s):
    return nameequiv.fold(s or "")


def _givens(p: fam.Person) -> set:
    out = set()
    for g in p.givens:
        nick = nameequiv.nickname_in_quotes(g)
        if nick:
            out.add(_fold(nick))
        for t in nameequiv.strip_quoted(g).split():
            t = _fold(t).strip(".")
            if len(t) > 1:
                out.add(t)
    return out


def _surnames(f: fam.Family, p: fam.Person) -> set:
    out = {_fold(s) for s in p.surnames + p.married_surnames if s}
    if (p.sex or "").upper().startswith("F"):
        out |= {_fold(f.people[s].surnames[0]) for s in p.spouses if f.people[s].surnames}
    return {s for s in out if s}


def _surname_match(a: set, b: set) -> bool:
    if a & b:
        return True
    for s in a:
        if {_fold(v) for v in nameequiv.surname_variants(s)} & b:
            return True
    return False


def _given_score(a: fam.Person, b: fam.Person) -> tuple[int, str | None]:
    ga, gb = _givens(a), _givens(b)
    if not ga or not gb:
        return 0, None
    fa = _fold(nameequiv.strip_quoted(a.givens[0]).split()[0]) if a.givens and nameequiv.strip_quoted(a.givens[0]).split() else ""
    fb = _fold(nameequiv.strip_quoted(b.givens[0]).split()[0]) if b.givens and nameequiv.strip_quoted(b.givens[0]).split() else ""
    if fa and fa == fb:
        return 40, "same first name"
    common = ga & gb
    if common:
        return 32, f"shared given name “{sorted(common)[0].title()}”"
    for x in ga:
        eq = {_fold(e) for e in nameequiv.given_equivalents(x)}
        if eq & gb:
            return 26, f"“{x.title()}” and “{sorted(eq & gb)[0].title()}” are forms of the same name"
    return 0, None


def _year(r):
    return None if not r else (r["lo"] + r["hi"]) / 2


def compare(fa: fam.Family, a: str, fb: fam.Family, b: str) -> tuple[int, list, bool]:
    """Score how likely person a (in tree A) and b (in tree B) are the same person. Returns (score, reasons, conflict)."""
    pa, pb = fa.people[a], fb.people[b]
    reasons = []
    if pa.sex and pb.sex and pa.sex[:1].upper() != pb.sex[:1].upper():
        return 0, ["different sex"], True
    if not _surname_match(_surnames(fa, pa), _surnames(fb, pb)):
        return 0, [], False
    gs, why = _given_score(pa, pb)
    if not gs:
        return 0, [], False
    score = gs + 20
    reasons.append(why)
    conflict = False
    for label, ra, rb in (("born", fa.birth(a), fb.birth(b)), ("died", fa.death(a), fb.death(b))):
        if not ra or not rb:
            continue
        exact = not ra.get("estimated") and not rb.get("estimated")
        gap = abs(_year(ra) - _year(rb))
        if exact and gap <= 1:
            score += 25
            reasons.append(f"{label} the same year ({int(_year(ra))})")
        elif gap <= 3:
            score += 10 if exact else 4
            reasons.append(f"{label} within {int(gap) or 1} years")
        elif exact and gap > 5:
            conflict = True
            reasons.append(f"{label} years differ ({int(_year(ra))} vs {int(_year(rb))})")
    bpa, bpb = fa.birth_place(a), fb.birth_place(b)
    if bpa and bpb and bpa.town and bpb.town and _fold(bpa.town) == _fold(bpb.town):
        score += 10
        reasons.append(f"both born in {bpa.town}")
    return score, reasons, conflict


def suggest(conn, target_pid: str, source_pid: str) -> dict:
    if target_pid == source_pid:
        raise ValidationError("Choose two different trees")
    ft, fs = fam.load(conn, target_pid), fam.load(conn, source_pid)
    by_surname: dict = {}
    for k, p in ft.people.items():
        for s in _surnames(ft, p):
            by_surname.setdefault(s, set()).add(k)
            for v in nameequiv.surname_variants(s):
                by_surname.setdefault(_fold(v), set()).add(k)
    cands: dict = {}
    for sk, sp in fs.people.items():
        pool = set()
        for s in _surnames(fs, sp):
            pool |= by_surname.get(s, set())
        for tk in pool:
            sc, why, conflict = compare(fs, sk, ft, tk)
            if sc and (not conflict or "different sex" not in why):
                cands[(sk, tk)] = {"base": sc, "why": why, "support": [], "conflict": conflict}

    def total(v):
        return v["base"] + min(30, 15 * len(v["support"]))
    # relatives that also match make a pair much more likely (two passes, so support can spread up and down the tree)
    for _ in range(2):
        best_for = {}
        for (sk, tk), v in cands.items():
            if total(v) >= 70 and not v["conflict"] and (sk not in best_for or total(v) > total(cands[(sk, best_for[sk])])):
                best_for[sk] = tk
        for (sk, tk), v in cands.items():
            sp, tp = fs.people[sk], ft.people[tk]
            v["support"] = [f"{rel} {fs.people[x].name} also matches"
                            for rel, a_list, b_list in (("parent", sp.parents, tp.parents), ("spouse", sp.spouses, tp.spouses), ("child", sp.children, tp.children))
                            for x in a_list if best_for.get(x) in b_list]
    # one-to-one, best first
    taken_s, taken_t, out = set(), set(), []
    for (sk, tk), v in sorted(cands.items(), key=lambda kv: (kv[1]["conflict"], -total(kv[1]))):
        sc = total(v)
        if sk in taken_s or tk in taken_t or sc < 60:
            continue
        if v["conflict"] and not v["support"]:
            continue    # same name but conflicting dates and no shared relatives: probably a different person
        taken_s.add(sk)
        taken_t.add(tk)
        level = CONFLICT if v["conflict"] else HIGH if sc >= 95 else POSSIBLE
        out.append({"source": fs.summary(sk), "target": ft.summary(tk), "score": sc, "level": level,
                    "reasons": v["why"] + v["support"],
                    # pre-selected: confident matches, and likely ones that two or more matching relatives back up
                    "recommended": level == HIGH or (level == POSSIBLE and len(v["support"]) >= 2)})
    order = {HIGH: 0, POSSIBLE: 1, CONFLICT: 2}
    out.sort(key=lambda o: (order[o["level"]], -o["score"]))
    return {"pairs": out, "source_people": len(fs.people), "target_people": len(ft.people),
            "source": [{"id": k, "name": p.name, "lifespan": fs.summary(k)["lifespan"]} for k, p in sorted(fs.people.items(), key=lambda kv: kv[1].name)],
            "target": [{"id": k, "name": p.name, "lifespan": ft.summary(k)["lifespan"]} for k, p in sorted(ft.people.items(), key=lambda kv: kv[1].name)]}


# ------------------------------------------------------------------ combining

def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def combine(conn, settings, target_pid: str, source_pid: str, pairs: list) -> dict:
    tgt = one(conn, "SELECT * FROM projects WHERE id = ?", (target_pid,))
    src = one(conn, "SELECT * FROM projects WHERE id = ?", (source_pid,))
    if not tgt or not src:
        raise NotFound("project")
    if target_pid == source_pid:
        raise ValidationError("Choose two different trees")
    s_people = {r["id"] for r in rows(conn, "SELECT id FROM persons WHERE project_id = ?", (source_pid,))}
    t_people = {r["id"] for r in rows(conn, "SELECT id FROM persons WHERE project_id = ?", (target_pid,))}
    same: dict = {}
    for pr in pairs or []:
        s, t = pr.get("source"), pr.get("target")
        if s not in s_people or t not in t_people:
            raise ValidationError("A chosen pair doesn't belong to these two trees")
        if s in same or t in same.values():
            raise ValidationError("Each person can be paired only once")
        same[s] = t
    created: dict = {}
    ts = now_iso()

    def add(table, data):
        insert(conn, table, data)
        created.setdefault(table, []).append(data["id"])

    def copy_row(table, r, **changes):
        cols = _cols(conn, table)
        data = {c: r[c] for c in cols if c in r.keys()}
        data.update(changes)
        add(table, data)
        return data["id"]
    stats = {"people_added": 0, "people_merged": len(same), "facts_added": 0, "facts_already_there": 0, "sources_added": 0,
             "relationships_added": 0, "relationships_already_there": 0}
    with Tx(conn):
        # places
        place_map = {}
        t_places = {(_fold(r["name"]), _fold(r["region"]), _fold(r["country"])): r["id"]
                    for r in conn.execute("SELECT * FROM places WHERE project_id = ?", (target_pid,))}
        for r in conn.execute("SELECT * FROM places WHERE project_id = ?", (source_pid,)).fetchall():
            k = (_fold(r["name"]), _fold(r["region"]), _fold(r["country"]))
            place_map[r["id"]] = t_places.get(k) or copy_row("places", r, id=new_id(), project_id=target_pid, created_at=ts, updated_at=ts)
            t_places.setdefault(k, place_map[r["id"]])
        # people
        person_map = dict(same)
        for r in conn.execute("SELECT * FROM persons WHERE project_id = ?", (source_pid,)).fetchall():
            if r["id"] in same:
                continue
            person_map[r["id"]] = copy_row("persons", r, id=new_id(), project_id=target_pid, created_at=ts, updated_at=ts)
            stats["people_added"] += 1
        # names (merged people: add names the target doesn't have)
        for r in conn.execute("""SELECT n.* FROM person_names n JOIN persons p ON p.id = n.person_id WHERE p.project_id = ?""", (source_pid,)).fetchall():
            tp = person_map[r["person_id"]]
            if r["person_id"] in same:
                have = {(_fold(x["given"]), _fold(x["surname"])) for x in conn.execute("SELECT given, surname FROM person_names WHERE person_id = ?", (tp,))}
                if (_fold(r["given"]), _fold(r["surname"])) in have:
                    continue
                copy_row("person_names", r, id=new_id(), person_id=tp, name_type=r["name_type"] if r["name_type"] != "birth" else "alias",
                         note=((r["note"] or "") + f" (from {src['name']})").strip(), created_at=ts)
            else:
                copy_row("person_names", r, id=new_id(), person_id=tp, created_at=ts)
        # merged people: fill in sex / living status / notes the target lacks
        for s, t in same.items():
            sp = one(conn, "SELECT * FROM persons WHERE id = ?", (s,))
            tp = one(conn, "SELECT * FROM persons WHERE id = ?", (t,))
            patch = {}
            if not tp["sex"] and sp["sex"]:
                patch["sex"] = sp["sex"]
            if tp["living_status"] == "unknown" and sp["living_status"] != "unknown":
                patch["living_status"] = sp["living_status"]
            if patch:
                created.setdefault("_person_patches", []).append({"id": t, "before": {k: tp[k] for k in patch}})
                update(conn, "persons", t, {**patch, "updated_at": ts})
        # sources
        source_map = {}
        for r in conn.execute("SELECT * FROM sources WHERE project_id = ?", (source_pid,)).fetchall():
            source_map[r["id"]] = copy_row("sources", r, id=new_id(), project_id=target_pid, research_log_id=None, duplicate_of_id=None,
                                           created_at=ts, updated_at=ts)
            stats["sources_added"] += 1
        # claims
        claim_map = {}
        existing = {}
        for r in conn.execute("SELECT * FROM claims WHERE project_id = ?", (target_pid,)):
            existing[_claim_key(r)] = r["id"]
        src_claims = conn.execute("SELECT * FROM claims WHERE project_id = ?", (source_pid,)).fetchall()
        for r in src_claims:
            pid = person_map[r["person_id"]]
            rel = person_map.get(r["related_person_id"]) if r["related_person_id"] else None
            new = dict(r)
            new.update(person_id=pid, related_person_id=rel, place_id=place_map.get(r["place_id"]), to_place_id=place_map.get(r["to_place_id"]))
            key = _claim_key(new)
            if key in existing:
                claim_map[r["id"]] = existing[key]
                if r["claim_type"] == "relationship":
                    stats["relationships_already_there"] += 1
                else:
                    stats["facts_already_there"] += 1
                continue
            if r["claim_type"] == "relationship" and rel and _reverse_rel_exists(conn, pid, rel, r["relationship_type"]):
                stats["relationships_already_there"] += 1
                claim_map[r["id"]] = None
                continue
            nid = copy_row("claims", new, id=new_id(), project_id=target_pid, created_at=ts, updated_at=ts)
            claim_map[r["id"]] = nid
            existing[key] = nid
            stats["relationships_added" if r["claim_type"] == "relationship" else "facts_added"] += 1
        # evidence links
        for r in conn.execute("""SELECT e.* FROM claim_evidence e JOIN claims c ON c.id = e.claim_id WHERE c.project_id = ?""", (source_pid,)).fetchall():
            cid, sid = claim_map.get(r["claim_id"]), source_map.get(r["source_id"])
            if not cid or not sid:
                continue
            if conn.execute("SELECT 1 FROM claim_evidence WHERE claim_id = ? AND source_id = ?", (cid, sid)).fetchone():
                continue
            copy_row("claim_evidence", r, id=new_id(), claim_id=cid, source_id=sid, created_at=ts, updated_at=ts)
        # questions, tasks, research log
        q_map = {}
        for r in conn.execute("SELECT * FROM research_questions WHERE project_id = ?", (source_pid,)).fetchall():
            q_map[r["id"]] = copy_row("research_questions", r, id=new_id(), project_id=target_pid, person_id=person_map.get(r["person_id"]),
                                      place_id=place_map.get(r["place_id"]), created_at=ts, updated_at=ts)
        log_map = {}
        for r in conn.execute("SELECT * FROM research_log WHERE project_id = ?", (source_pid,)).fetchall():
            log_map[r["id"]] = copy_row("research_log", r, id=new_id(), project_id=target_pid, person_id=person_map.get(r["person_id"]),
                                        question_id=q_map.get(r["question_id"]), run_id=None, created_at=ts, updated_at=ts)
        for r in conn.execute("SELECT * FROM tasks WHERE project_id = ?", (source_pid,)).fetchall():
            copy_row("tasks", r, id=new_id(), project_id=target_pid, person_id=person_map.get(r["person_id"]), question_id=q_map.get(r["question_id"]),
                     created_at=ts, updated_at=ts)
        for old, new in source_map.items():
            lid = one(conn, "SELECT research_log_id FROM sources WHERE id = ?", (old,))["research_log_id"]
            if lid and log_map.get(lid):
                update(conn, "sources", new, {"research_log_id": log_map[lid]})
        # attachments: copy the files too, so each tree owns its copy
        adir = Path(settings.attachments_dir)
        owner_maps = {"person": person_map, "source": source_map, "log": log_map}
        for r in conn.execute("SELECT * FROM attachments WHERE project_id = ?", (source_pid,)).fetchall():
            owner = owner_maps.get(r["owner_type"], {}).get(r["owner_id"])
            if not owner:
                continue
            src_file = (adir / r["stored_path"]).resolve()
            if adir.resolve() not in src_file.parents or not src_file.exists():
                continue
            rel = f"{target_pid}/{new_id()}{src_file.suffix}"
            (adir / target_pid).mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, adir / rel)
            created.setdefault("_files", []).append(rel)
            copy_row("attachments", r, id=new_id(), project_id=target_pid, owner_id=owner, stored_path=rel, created_at=ts)
        rid = new_id()
        insert(conn, "combine_runs", {"id": rid, "target_project_id": target_pid, "source_project_id": source_pid, "source_name": src["name"],
                                      "pairs_json": json.dumps([{"source": s, "target": t} for s, t in same.items()]),
                                      "created_json": json.dumps(created), "stats_json": json.dumps(stats), "created_at": ts})
        update(conn, "projects", target_pid, {"updated_at": ts})
    return get_run(conn, rid)


def _claim_key(r) -> tuple:
    """Two facts are 'the same' when type, person, date as written, place, related person and value all match."""
    g = (lambda k: r[k] if k in (r.keys() if hasattr(r, "keys") else r) else None)
    return (g("person_id"), g("claim_type"), _fold(g("date_text")), g("place_id"), g("related_person_id"), g("relationship_type"),
            _fold(g("value_text")) if g("claim_type") not in ("name",) else _fold(g("value_text")))


def _reverse_rel_exists(conn, pid, rel, rtype) -> bool:
    """'A child of B' is the same relationship as 'B parent of A'; spouse is symmetrical."""
    opposite = {"child": "parent", "parent": "child", "spouse": "spouse", "sibling": "sibling"}.get(rtype)
    if not opposite:
        return False
    return bool(conn.execute("""SELECT 1 FROM claims WHERE claim_type = 'relationship' AND status != 'rejected' AND
                                ((person_id = ? AND related_person_id = ? AND relationship_type = ?) OR
                                 (person_id = ? AND related_person_id = ? AND relationship_type = ?))""",
                             (rel, pid, opposite, pid, rel, rtype)).fetchone())


def get_run(conn, rid: str) -> dict:
    r = one(conn, "SELECT * FROM combine_runs WHERE id = ?", (rid,))
    if not r:
        raise NotFound("combine")
    r.pop("created", None)
    return r


def list_runs(conn, target_pid: str) -> list:
    out = rows(conn, "SELECT id, target_project_id, source_project_id, source_name, stats_json, pairs_json, created_at, undone_at FROM combine_runs "
                     "WHERE target_project_id = ? ORDER BY created_at DESC", (target_pid,))
    return out


UNDO_ORDER = ["attachments", "tasks", "claim_evidence", "claims", "research_log", "research_questions", "sources", "person_names", "persons", "places"]


def undo(conn, settings, rid: str) -> dict:
    r = one(conn, "SELECT * FROM combine_runs WHERE id = ?", (rid,))
    if not r:
        raise NotFound("combine")
    if r["undone_at"]:
        raise ValidationError("This combine was already undone")
    later = one(conn, "SELECT id FROM combine_runs WHERE target_project_id = ? AND created_at > ? AND undone_at IS NULL", (r["target_project_id"], r["created_at"]))
    if later:
        raise ValidationError("Undo the later combine into this tree first")
    created = r["created"]
    with Tx(conn):
        for table in UNDO_ORDER:
            ids = created.get(table) or []
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                conn.execute(f"DELETE FROM {table} WHERE id IN ({','.join('?' * len(chunk))})", chunk)
        for p in created.get("_person_patches") or []:
            update(conn, "persons", p["id"], p["before"])
        update(conn, "combine_runs", rid, {"undone_at": now_iso()})
    adir = Path(settings.attachments_dir)
    for rel in created.get("_files") or []:
        f = (adir / rel).resolve()
        if adir.resolve() in f.parents and f.exists():
            f.unlink()
    return get_run(conn, rid)
