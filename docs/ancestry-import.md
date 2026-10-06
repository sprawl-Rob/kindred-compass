# Importing from Ancestry and other GEDCOM files

Kindred Compass imports GEDCOM exports from **Ancestry.com**, **Family Tree Maker**, **RootsMagic** and other genealogy programs.

**An import is a one-time local snapshot.** It is not a connection to Ancestry. Nothing you change here goes back to Ancestry, and nothing you change on Ancestry arrives here until you export again and run a *repeat import*.

## The workflow

1. **Import** (top navigation). Choose your inputs:
   - the GEDCOM file (`.ged`), or a ZIP that contains one (`.zip` / GEDCOM 7 `.gdz`);
   - optionally, a media folder or a media ZIP.
2. **Preview.** Nothing is written to your research yet. The preview shows:
   - **Detected:** the exporting program, tree name and id, GEDCOM version, declared and actual character set, line count, and whether the file ends properly.
   - **Counts:** people, families, parent–child and partner links (by relationship type: biological, adopted, step, foster…), events and facts, names, sources, citations, repositories, notes, media references (local vs online), Ancestry record references, and parse failures.
   - **Problems:** warnings (e.g. references to records missing from the file), lines that could not be parsed (with line numbers), and **unsupported tags** (tag path, count, example line). Unsupported tags are kept in the original record; nothing is discarded.
   - **Mapped program-specific tags,** e.g. `_MILT` → military service, `_FREL`/`_MREL` → parent relationship type, `_APID` → Ancestry record reference.
   - **Media matching** for every referenced file: matched, missing, ambiguous, online (not downloaded), or unsupported type. Also listed: supplied files that the GEDCOM never references (these are not attached to anyone).
   - **Representative profiles.** People chosen to cover the hard cases: the first/home person, multiple marriages, non-biological parents, uncertain dates, non-ASCII names, alternative facts, media. Each is shown *as it will be imported* next to *the original lines of the file*.
3. **Import.**
   - A safety backup is made first.
   - The first import of a tree goes into a **new, separate project**, so it never mixes with your other work until you decide.
4. **Check.** After importing, the import page shows the report and a review queue. The migration is labelled **"Not yet confirmed"** until you tick *I have checked the import report and the representative profiles*.
5. **Undo** is available on the import page.
   - Undoing a first import deletes the imported project and its attachments, after a backup.
   - Undoing a repeat import removes the rows it added and restores rows it changed. Anything you edited since the import is kept and listed.

Every imported person has an **"Imported data — side by side with the original file"** panel. It shows each claim and name next to the exact GEDCOM lines (with line numbers) it came from, plus the complete original record.

## How data is mapped

| GEDCOM | In Kindred Compass |
|---|---|
| `INDI` | Person. Primary name becomes the display name; `SEX` is kept. Living status is *deceased* if death or burial is recorded, otherwise *unknown* (treated as possibly living and private). |
| `NAME` (+ `GIVN`, `SURN`, `NPFX`, `NSFX`, `NICK`, `TYPE`, `ROMN`, `FONE`, `TRAN`, `_MARNM`) | Names, typed as birth / married / alias / variant / original-script. Unicode and ANSEL names are preserved. |
| Events and facts (`BIRT`, `CHR`, `DEAT`, `BURI`, `RESI`, `CENS`, `IMMI`, `NATU`, `OCCU`, `EVEN`+`TYPE`, `FACT`, `_MILT`, …) | **Claims** with origin "import", status **working** (relationships: **tentative**), and a note saying they are recorded in the tree and not independently verified. Two births in the file become two claims and are flagged as a conflict; nothing is merged. |
| `DATE` | The original expression is stored verbatim (`ABT 1852`, `BET 1853 AND 1856`, `1750/51`, `INT 1890 (…)`, `@#DJULIAN@ …`). A search window and a qualifier (about / calculated / estimated / before / after / between / exact) are derived from it. |
| `PLAC` | The full place string is kept. Country, state, county and town are split out only when the pattern is unambiguous (e.g. `Town, County, State, USA`). `MAP` coordinates are kept in the place notes. |
| `FAM` | Partner relationship between `HUSB` and `WIFE`; couple events (`MARR`, `DIV`, …) on both partners. Each child gets a *child of* claim for each parent, carrying the relationship type from `_FREL`/`_MREL` or `PEDI` (biological, adopted, step, foster, guardian, sealed). If none is stated, it shows *not stated*. Adoptive and step parents are not counted as conflicting biological parents. |
| `SOUR` record + citation (`PAGE`, `DATA`/`TEXT`, `QUAY`, `NOTE`, `_APID`) | One **source** per distinct citation. Fields: title, author, publication, repository and call number from the master source; page reference; citation text; tree quality rating; the Ancestry record reference (`_APID`) kept in the citation text and original record. Linked to the fact as *supports* evidence with identity **uncertain** and assessment **unassessed**. |
| `REPO` | Repository name and call number on the source. |
| `NOTE` (inline and records) | Person notes and fact statements; source notes go into source provenance. |
| `OBJE` / `FILE` | Media references (see below). |
| `_UID`, `UID`, `RIN`, `REFN`, `AFN`, `EXID` | Kept as identifiers *scoped to this tree's import lineage*. Used to recognise records on repeat imports. |
| Anything else | Kept verbatim in the original record and listed under "Unsupported content". Custom event-like tags (with a `DATE` or `PLAC`) are also imported as generic facts. |

No AI is involved in parsing, mapping, matching or linking.

## Media

- **Local references** (`C:\…\Ferris Media\photo.jpg`, `media/scan.png`) are matched against the files you supply:
  - The longest matching run of trailing folder/file names wins, ignoring case.
  - If several supplied files tie, the reference is **ambiguous** and goes to review, where you choose a file or leave it unattached.
  - A match on file name alone is only accepted if exactly one supplied file has that name, and it is labelled as such.
- **Online references** (`https://…`, e.g. Ancestry media pages) are listed as *online — not downloaded*. The app never fetches content that needs your Ancestry login.
- **Attachments only follow explicit references.** Files are attached only to the person, family or source whose GEDCOM record references them, never by guessing from a file name. Supplied files that nothing references are reported and left alone.
- **Supported file types** follow the attachment allow-list: images, PDF, text, audio/video, Word/ODT/RTF. Other types are reported as unsupported. Matched files are copied into the app's managed storage.

## Repeat imports (no duplicates)

Choose **"Update of earlier import: <tree>"** when uploading, or pick the tree in the preview. Each originating tree is a separate **lineage**.

**Identifier scope.**
- Record identifiers (`@I123@`, `_UID`, `RIN`) are compared only within that lineage.
- An identifier match also needs a compatible name and birth window.
- Identifiers are not assumed to be stable or globally unique. A different tree that reuses `@I101@` is a different lineage and project.

**How people are matched:**

| Situation | What happens |
|---|---|
| Same stable id (`_UID` etc.) | Matched. |
| Same record id and consistent name/birth | Matched. |
| Same record id but a different person | Imported separately and listed for review. The person who previously had that id is reported as no longer in the export. |
| Different id, same name and compatible birth | Imported separately and listed for review. Accepting moves the new facts onto the earlier person; rejecting keeps them apart and remembers that decision. |
| No match | Imported as a new person. |

**How facts, people and records are handled:**
- **Facts** are recognised by fingerprint (tag, type, date text, place text, value), so re-importing the same file adds nothing.
- **New facts** are added.
- **Facts missing from the new export** are kept and listed for review, where you can mark them rejected.
- **Person fields** (name, sex, notes) changed in the export are updated only if you have not edited them locally. Otherwise the change is listed as a conflict and your value is kept.
- **People missing from the new export** are kept and listed.

## Safety

- **Archives:** extraction refuses absolute paths, `..` traversal, symbolic links, encrypted entries, more than 50,000 entries, more than 8 GB expanded, and suspicious compression ratios (ZIP bombs). `__MACOSX` and `.DS_Store` entries are ignored.
- **The original upload is stored byte-for-byte.** You can download it from the import page, and it is included in backups (`data/imports/<id>/original/`).
- **Text from the file is always treated as data:** displayed as text, never executed or interpreted as instructions.

## What an Ancestry export contains, and what needs a separate transfer

Each point below has a source, with its evidence level noted. The full research notes and URLs are in `tools/research/gedcom_exports.md`. Evidence levels:
- **official** — Ancestry's help pages;
- **sample** — seen in a real 2024 "Export tree" file;
- **unconfirmed** — not documented by Ancestry.

### Exporting

- **Steps:** Trees → choose the tree → More (⋯) → Tree Settings → *Export tree* → *Export* → *Download Your GEDCOM File*. Only the tree owner can export. *(official)*
- **The file arrives inside a ZIP.** You can import the ZIP directly. *(official)*
- **There are no export options** — the whole tree is exported, living people included. *(secondary sources; consistent with the sample)*

### What the file contains (and how it is imported)

| Ancestry data | In the export? | How Kindred Compass imports it |
|---|---|---|
| People, names (`GIVN`/`SURN`/`NSFX`), sex | Yes *(sample)* | People and names; Ancestry person ids (`@I112187149819@`) are kept as record ids for this tree. |
| Facts and events (birth, death, residence, `_MILT`, `_EMPLOY`, `EVEN` + `TYPE Arrival`/`Departure`, …) | Yes *(sample)* | Claims. Arrival → immigration, Departure → emigration, `_EMPLOY` → occupation, `_MILT` → military. |
| Alternative facts (two births, several residences) | Yes *(sample)* | Kept side by side; birth/death conflicts are flagged. Ancestry's "preferred" choice is not exported, so none is assumed. |
| Dates exactly as typed (`abt 1880`, `About 1884`, `Before 1951`, `2 Juli 1850`, `1910-1939`, `Jul Abt 1874`, `??`) | Yes *(sample)* | Original text kept. Words and ranges are interpreted case-insensitively; anything unclear is labelled "interpreted loosely" or "could not be interpreted". |
| Parents and children; adopted and step | Yes. `_FREL`/`_MREL` on the family's child line (`adopted`, `step`, `unknown`); `ADOP Y` on adopted children. Biological links carry no tag. *(sample)* | Relationship type kept. Untagged links are shown as **not stated** (with a note that Ancestry omits the tag for biological links) rather than silently assumed. |
| Notes on people and facts | Yes *(sample)* | Person notes and fact statements; long notes split with `CONC` are rejoined. |
| Sources, repositories, citations (`PAGE`, `DATA/TEXT`, `DATA/WWW`) | Yes *(sample)* | Sources linked to facts as unreviewed evidence. |
| Ancestry record references `_APID 1,<database>::<record>` (sometimes several per citation) | Yes *(sample)* | All kept in the citation text and original record. **No Ancestry web address is built from them.** The only published pattern is community-sourced, not from Ancestry. Links written in the file (`WWW`, FTM's `_LINK`) are used as-is. |
| Tree name, tree id, description (`_TREE`, `RIN`, `NOTE`) | Yes *(sample)* | Shown in the preview; used to recognise repeat imports of the same tree. |
| Photos, documents, stories | **No — only references.** Media records have an empty `FILE` and an Ancestry media id (GUID in `RIN`); stories appear as empty placeholders. *(official: "photos, media, and similar items are not included"; sample)* | Listed as **"Held on Ancestry — file not in the export"** with the media id. Never downloaded. |
| Record images from Ancestry collections | **No.** Only the `_APID` reference. *(sample)* | — |
| DNA results, DNA matches, ThruLines, ethnicity | **No.** Raw DNA is a separate download from DNA Settings; Ancestry states that DNA match lists cannot be exported. *(official)* | — |
| Hints, comments, messages | **Not seen** in exports and not documented as exported. *(unconfirmed)* | — |
| Ancestry person tags (`_MTTAG` records) | Possibly present as top-level records *(secondary)* | Reported as unsupported top-level records, kept in the original file. |

### Bringing media across separately

Ancestry offers no "download all media" option *(secondary)*. Options:
- **Save items individually** from Ancestry's media viewer.
- **Sync the tree to Family Tree Maker or RootsMagic** (both download media). Then export a GEDCOM from that program with media links, and supply its media folder here. FTM writes absolute Windows paths such as `C:\FTM\<tree> Media\photo.jpg`; these are matched by folder and file name.

Third-party browser extensions also exist. They are not endorsed or used by this app.

### Other programs

- **Family Tree Maker** (2019/2024): `1 SOUR FTM`, UTF-8 with a byte-order mark (older versions: `ANSI`). It writes:
  - `_FREL`/`_MREL` capitalised (`Natural`, `Step`, `Guardian`, …);
  - `_PHOTO` for the primary photo, which is attached if supplied;
  - `_LINK` (an Ancestry URL) and `_JUST` (justification) on citations;
  - `FSID` (FamilySearch id, kept as an identifier);
  - many custom facts.
- **RootsMagic:** `1 SOUR RootsMagic`, `_UID` (used to recognise records on repeat imports), and source-template tags (`_TMPLT`, `_SUBQ`, `_BIBL`). Media paths may start with `?`, `~` or `*` (RootsMagic folder shortcuts); these are ignored when matching. RootsMagic exports GEDCOM 5.5.1, not 7.

### Still unconfirmed

These are handled defensively:
- the file name inside Ancestry's ZIP (any `.ged` inside is accepted);
- whether `FILE` is ever filled with a URL (URLs would be listed as online, not fetched);
- the meaning of the `1,` prefix in `_APID` and of `_ORIG`/`_ATL`/`_ENV` (all kept verbatim);
- how people point to `_MTTAG` records (reported as unsupported);
- the full value lists for `_FREL`/`_MREL` (unknown values are kept as written and typed "other").

## Limitations

- GEDCOM 7 `.gdz` archives are read as ZIPs. GEDCOM 7-only structures such as `SNOTE`, `EXID` and `TRAN` are understood; less common 7.0 features are preserved but reported as unsupported.
- Place splitting is deliberately conservative. Ambiguous strings keep only the full text.
- Sources are created per distinct citation, not per master source. Master-source fields are copied onto each.
- The project JSON export does not carry import history. Use a full backup to keep it, including the original GEDCOM files.
- **Not yet tested on your export.** The import was tested on synthetic fixtures built to match real exports:
  - an Ancestry 2024 export, using its real header and structure;
  - Family Tree Maker files with media folders;
  - an ANSEL-encoded RootsMagic file;
  - a 5,000-person tree.

  Run your own export through the preview, and check the report and the representative profiles, before treating the migration as complete.
