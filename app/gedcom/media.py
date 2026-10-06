"""Safe archive handling and GEDCOM media-reference matching.

Matching rules (deterministic, conservative):
* Only files that the GEDCOM explicitly references are attached, and only to the
  person/source/family that references them. Supplied files are never attached to
  people by name alone.
* A reference matches a supplied file by the longest trailing run of path components
  (case-insensitive). If several files tie for the best match it is *ambiguous* and goes
  to review. A match on the file name alone is allowed only when exactly one supplied
  file has that name, and is reported as "matched by file name only".
* http(s) references are *remote*: recorded, never fetched (Ancestry content needs your login).
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILES = 50_000
MAX_TOTAL_BYTES = 8 * 1024 ** 3
MAX_RATIO = 250            # uncompressed / compressed, per member above 1 MB
IGNORED = ("__MACOSX/", ".DS_Store", "Thumbs.db", "desktop.ini")


class ArchiveError(Exception):
    pass


def safe_relpath(name: str) -> str | None:
    """Normalise an archive/upload relative path; None if unsafe."""
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return None
    parts = [p for p in PurePosixPath(n).parts if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def is_ignored(rel: str) -> bool:
    return any(rel.startswith(i) or rel.endswith("/" + i) or rel == i for i in IGNORED) or "/__MACOSX/" in rel


def safe_extract(zip_path: Path, dest: Path, members: list[str] | None = None) -> dict:
    """Extract a ZIP safely. Returns {"files": [...], "skipped": [{name, reason}]}."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    files, skipped, total = [], [], 0
    try:
        z = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ArchiveError("The file is not a valid ZIP archive.")
    with z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            raise ArchiveError(f"Archive has {len(infos)} entries; the limit is {MAX_FILES}.")
        for info in infos:
            name = info.filename
            if info.is_dir():
                continue
            if members is not None and name not in members:
                continue
            rel = safe_relpath(name)
            if rel is None:
                skipped.append({"name": name, "reason": "unsafe path (absolute or contains ..)"})
                continue
            if is_ignored(rel):
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                skipped.append({"name": name, "reason": "symbolic link (not extracted)"})
                continue
            if info.flag_bits & 0x1:
                skipped.append({"name": name, "reason": "encrypted entry"})
                continue
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ArchiveError("Archive expands beyond the 8 GB safety limit.")
            if info.file_size > 1_000_000 and info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
                raise ArchiveError(f"{name} has a suspicious compression ratio (possible ZIP bomb); import stopped.")
            target = (root / rel).resolve()
            if root not in target.parents:
                skipped.append({"name": name, "reason": "path escapes the import folder"})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with z.open(info) as src, open(target, "wb") as out:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > info.file_size + 1024:
                        raise ArchiveError(f"{name} is larger than its declared size; import stopped.")
                    out.write(chunk)
            files.append(rel)
    return {"files": files, "skipped": skipped}


def list_zip(zip_path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(zip_path) as z:
            return [i.filename for i in z.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        raise ArchiveError("The file is not a valid ZIP archive.")


def inventory(folder: Path) -> list[str]:
    if not folder.exists():
        return []
    out = []
    for p in folder.rglob("*"):
        if p.is_file() and not p.is_symlink():
            rel = p.relative_to(folder).as_posix()
            if not is_ignored(rel):
                out.append(rel)
    return sorted(out)


def _components(ref: str) -> list[str]:
    r = ref.replace("\\", "/")
    r = re.sub(r"^[A-Za-z]:", "", r)
    r = re.sub(r"^file://", "", r)
    # RootsMagic stores media paths with ? (media folder), ~ (home) and * (database folder) prefixes.
    return [p for p in r.split("/") if p and p not in (".", "?", "~", "*")]


def is_remote(ref: str) -> bool:
    return bool(re.match(r"^(https?|ftp)://", (ref or "").strip(), re.I))


def match_reference(ref: str, files: list[str]) -> dict:
    """Return {status, path, candidates, how}."""
    if not ref:
        return {"status": "missing", "path": None, "candidates": [], "how": "empty reference"}
    if is_remote(ref):
        return {"status": "remote_not_fetched", "path": None, "candidates": [], "how": "remote URL — not downloaded"}
    rc = [c.lower() for c in _components(ref)]
    if not rc:
        return {"status": "missing", "path": None, "candidates": [], "how": "empty reference"}
    best, best_len = [], 0
    for f in files:
        fc = [c.lower() for c in f.split("/")]
        n = 0
        while n < min(len(fc), len(rc)) and fc[-1 - n] == rc[-1 - n]:
            n += 1
        if n == 0:
            continue
        if n > best_len:
            best, best_len = [f], n
        elif n == best_len:
            best.append(f)
    if not best:
        return {"status": "missing", "path": None, "candidates": [], "how": "no supplied file has this name"}
    if len(best) > 1:
        return {"status": "ambiguous", "path": None, "candidates": sorted(best)[:20],
                "how": f"{len(best)} supplied files match equally ({best_len} path component{'s' if best_len > 1 else ''})"}
    if best_len > 1:
        how = "matched by folder and file name"
    elif len(rc) == 1:
        how = "reference gives only a file name; exactly one supplied file has it"
    else:
        how = "matched by file name only — folders differ (exactly one supplied file has this name)"
    return {"status": "matched", "path": best[0], "candidates": best, "how": how}


def copy_into(src_root: Path, rel: str, dest_dir: Path) -> Path:
    src = (src_root / rel).resolve()
    if src_root.resolve() not in src.parents:
        raise ArchiveError("Media path escapes the import folder")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / os.path.basename(rel)
    shutil.copyfile(src, out)
    return out
