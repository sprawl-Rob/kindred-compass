# Kindred Compass

A local-first genealogy research app that keeps working out what to find next about your family, and finds some of it itself.

The app is built around three screens:

1. **Home: what to research next.** It shows two lists:
   - **Brick walls:** ancestors on your direct line with no parents yet.
   - **Records to find:** records your tree doesn't have, closest relatives first, each with a ready-made search.
2. **Family tree.** A pedigree you can click through.
3. **Person page.** It has five parts:
   - **Family:** parents, spouses, children and siblings.
   - **Record checklist:** every census, vital record, immigration, naturalization, draft and Social Security record the person *should* appear in, given their dates and places, marked found ✓ or missing ○. For each missing record it shows where to look, their likely age and household, what the record would tell you, and searches with the right collection, name, birth years and place filled in.
   - **Finding parents:** for brick walls, the records most likely to name the parents, in order.
   - **Leads:** possible records found by research runs.
   - **Name variations:** nicknames, abbreviations, anglicized forms and surname spellings to search.

4. **Bringing back what you find elsewhere:** the app can't read Ancestry, FamilySearch or American Ancestors for you, but you can bring back what you're viewing:
   - **I found it:** a button on every checklist item. Paste the record's details from the record page; **Add a record** on the person's page does the same.
   - **Clip to Kindred Compass:** a bookmark button (More → Clip a record) that sends the record page you're viewing to the app in one click.
   - **What the app reads:** the record's fields (name, age, birth, residence, immigration, occupation, death, burial, spouse, parents) and the household. It matches household members to relatives already in your tree, so you can tick which facts and people to add.
   - **What it saves:** the record as a source with a citation, link and transcription, and every added fact as evidence. The checklist item turns ✓.
5. **Documents:** import certificates, letters, photos of records and scans (JPEG, PNG, HEIC, TIFF or PDF).
   - **Importing:** drag files anywhere onto the app, onto the Documents page, or onto a person's page.
   - **Reading the text:** done on your Mac with Apple's built-in text recognition; nothing is uploaded. PDFs that already contain text use it directly.
   - **What it works out:** the document type, labelled fields (child, father, mother, groom, bride, deceased, dates, places, informant, officiant) and which people in your tree it names.
   - **Read with AI (optional):** for forms (e.g. a DD-214), faded pages or handwriting, your OpenAI or Anthropic model can read the page images. The preview shows exactly what will be sent, and documents that look sensitive (Social Security or service numbers, recent dates) need an extra confirmation. The model is told not to write out ID numbers, and the app masks any that appear. The AI's reading is shown beside the image, with its fields and uncertain parts, for you to use or ignore.
   - **Filing it with a person:** the text is shown next to the image so you can correct it. The document becomes a source, with the image attached and the text as its transcription, and you choose which facts and relatives to add. It can also be noted on everyone else it mentions.
6. **Search:** search every source for a name, years and place, not tied to anyone in the tree.
   - **Automatic searches:** the app runs its own searches (the 1950 and Irish censuses, newspapers, books and others), using common forms and spellings of the name.
   - **Every other source:** each source in the directory that covers the place and years is listed, with the search pre-filled where the URL format is verified, or copy-ready search terms to paste. Mark the sources you're a member of (American Ancestors, NYG&B, a county historical society, Ancestry and so on), and they're listed first everywhere.
   - **Adding results:** any result can be **added to the tree as a new person** (optionally as the child, parent, spouse or sibling of someone already there) or **attached to an existing person**. Results you haven't dealt with wait in **Leads**.
   - **From a person:** the **Search sources** button on a person's page opens this screen pre-filled with their name, years and place.

Everything else is under **More**: the original directory, the research log, sources and evidence, next-search suggestions, import and settings.

AI assistance (OpenAI or Anthropic) is optional, **off by default**, and every AI result is a proposal you review.

**Research that runs itself:** "Research automatically" (or a checklist item's **Search now** button) plans and runs searches against archives with public search APIs. These include **the 1950 U.S. census** and **the 1901/1911 census of Ireland**; Library of Congress newspapers and books; Internet Archive books; and Papers Past. DPLA, the National Archives Catalog, Trove and Europeana also work once you add your free keys. Searches use the names records actually used: married names, "Mrs. <husband>", nicknames and anglicized forms, and surname spellings. The app reads the item text, checks each result against what you know (names, ages, years, places, same-name traps), auto-saves strong matches as clearly-unreviewed sources, logs every search, and hands back the searches only you can run. An optional **AI research assistant** (your OpenAI/Anthropic key) plans and adapts searches, reads results, can search the open web, and records quoted findings that the app verifies. See **[docs/research-runs.md](docs/research-runs.md)**.

**Combining trees:** under More → Combine trees (or the Family tree page) you can bring one tree into another, for example your mother's side into your father's tree:
- **Suggested matches:** the app proposes who appears in both trees, using names (including nicknames and spellings), dates, birthplaces and matching relatives.
- **Your confirmation:** each pair is shown for you to confirm. Pairs where the family matches but a date disagrees are flagged rather than hidden.
- **The result:** confirmed pairs become one person. Facts that are identical aren't duplicated, and facts that differ are kept side by side.
- **Safe to try:** the other tree is left unchanged, and you can undo a combine.

**Importing existing research:** Ancestry tree exports, Family Tree Maker and RootsMagic GEDCOMs (plain or zipped, with an optional media folder) can be imported. So can family-tree **box charts saved as PDF** (e.g. Family Tree Maker ancestor charts): relationships are read from the boxes and the lines connecting them. You get a full preview first; the import goes into its own project and can be undone; repeat imports don't create duplicates. Imports are one-time local snapshots, not a sync with Ancestry. See **[docs/ancestry-import.md](docs/ancestry-import.md)**.

---

## Install and launch

You need Python 3.10 or newer (developed on 3.14, macOS).

```bash
cd ~/Documents/Claude/Projects/Genes
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python -m app
```

The app opens at **http://127.0.0.1:8765/**. It listens only on your own computer, not your network. Options:

```bash
.venv/bin/python -m app --port 8800 --data-dir ~/GenealogyData --no-browser
```

There is no build step. The UI is plain ES modules plus a vendored copy of Preact/htm (`static/vendor/`), so nothing is fetched from the internet at runtime.

**Why this stack?** It is the same FastAPI + SQLite combination used by your other local app. Data stays in Python's standard-library SQLite file, the UI needs no Node toolchain, and the whole app is one process on one machine, which suits a local-first research tool you'll keep for years.

---

## Where your data lives

Everything is under one data folder. It defaults to `./data`, and you can change it with `--data-dir` or `KINDRED_DATA_DIR`.

| Path | Contents |
|---|---|
| `data/kindred.sqlite3` | All research data, the directory, settings and the AI run history (SQLite, WAL mode) |
| `data/attachments/<project-id>/<attachment-id>.<ext>` | Uploaded files, under generated names. The original names, SHA-256 hashes and owner links are kept in the database. |
| `data/backups/*.zip` | Backups made from the app, plus automatic safety backups |
| `data/imports/<import-id>/original/` | Each uploaded GEDCOM/ZIP, stored byte-for-byte |
| `data/imports/<import-id>/media/` | Staged media from the import, kept so ambiguous matches can be resolved later |

**API keys are never stored in the data folder.** They go in the macOS Keychain (or Windows Credential Manager or Secret Service) via `keyring`. You can also supply them as `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` environment variables. They never appear in exports, backups, browser storage, or logs.

**Storage model.** The schema is in `app/migrations/001_init.sql`. Migrations are numbered SQL files, and the applied version is tracked in `PRAGMA user_version`. Before any migration runs on an existing database, the app copies it (`kindred.pre-migration-vN.sqlite3`).

Main tables:
- **Directory:** `providers` and `collections` (kept separate), `collection_relations`, `directory_history`, `pathways`.
- **Workspace:** `projects`, `places`, `persons`, `person_names`, `claims`, `research_questions`, `tasks`, `bookmarks`, `research_log`.
- **Import (migration 002):** `import_lineages` (one per originating tree), `import_batches`, `import_records` (original GEDCOM records with identifiers scoped to the lineage), `import_links` (each imported row ↔ its original lines), `import_changes` (for undo), `import_media`, `import_review_items`.
- **Evidence:** `sources`, `claim_evidence`, `attachments`.
- **Settings and AI:** `settings`, `ai_runs`, `ai_proposals`.

## Backup and restore

Go to **Settings → Data & backups**.

- **Create backup now.** Writes a `.zip` containing a consistent SQLite snapshot, every attachment, the original import files, and a `manifest.json` with SHA-256 checksums.
- **Restore.** Pick a backup from the list or upload a `.zip`, then type `RESTORE` to confirm. The archive is validated first:
  - checksums
  - SQLite integrity check
  - no unsafe paths
  - schema version not newer than the app

  A safety backup of your current data is always made before anything is replaced.
- **Export this project (JSON)** includes its attachments. **Import a project** always creates a *new* project with fresh ids, so it never overwrites work.
- **Full export / full import** covers all data. Full import replaces everything (type `REPLACE`), after a safety backup.
- **CSV exports** are available for the research log and the resource directory. Spreadsheet-formula injection is neutralised.

Deleting a project also makes a backup first.

## Maintaining the directory

- Go to **Directory** (top navigation) to add, edit, archive, restore and verify entries without editing code.
  - **Verify** records the date and what you checked.
  - **Check link** makes one request to the official URL and records link health.
- Providers and collections are separate. One provider, such as FamilySearch, has several collections: Historical Records, Full-Text Search, Catalog, Wiki.
- **Unknown is explicit.** Empty coverage means *unknown*, not "none". Unknown access is stored as `unknown`, and empty rights notes mean *unknown*.
- **Pre-filled search links.** A template is only used if its "verified" box is ticked. Otherwise the app opens the provider's search page and offers a copyable query.
- **Seed data is versioned** (`app/seed/directory_seed.json`, built by `tools/build_seed.py`; the raw research findings are in `tools/research/`). The app applies a newer seed version automatically at startup, and you can re-apply it from the Directory page.
  - Updates are idempotent.
  - A field you edited is never overwritten (tracked per field).
  - Archived entries stay archived.
  - Nothing is deleted.
- To update the seed: edit `tools/build_seed.py`, bump `VERSION`, then run:

  ```bash
  .venv/bin/python tools/build_seed.py
  ```

## What actually works — integrations

| Kind | Status |
|---|---|
| Searching this app's directory | Works (local) |
| **Live retrieval: Library of Congress — Chronicling America** | **Works.** Uses the documented public loc.gov JSON API (no key). Verified with live queries on 2026-10-05; the API often takes 5–35 seconds to respond. Requests are user-initiated, one page at a time, and capped by the app at 10 per minute, below the documented limit of 20 per minute. Results show metadata and OCR snippets with links back to loc.gov. |
| Pre-filled provider searches (URL patterns verified with real test queries on 2026-10-05) | FamilySearch Historical Records, FamilySearch Research Wiki, Ancestry Card Catalog, National Archives Catalog, Find a Grave (name and birth year only; its place filter can't be set by URL), BLM GLO Records (new portal launched July 2026), Chronicling America, DPLA, TNA Discovery, Papers Past, Digitalarkivet, Geneanet |
| **Automatic research runs / AI research assistant** | Library of Congress books, Internet Archive search-inside (Open Library) and Papers Past (DigitalNZ) work without keys and were tested live 2026-10-05. DPLA, National Archives Catalog, Trove and Europeana adapters need your free keys and have **not** been tested live (use Settings → Archives → Test connection). See docs/research-runs.md. |
| Everything else | Outbound link to the provider's own search page, plus a copyable query and name variants. **No automated retrieval.** |
| Not implemented (documented APIs exist but need keys or approval) | Trove API (needs a key), DPLA API (needs a key), FamilySearch API (partner approval). DigitalNZ says no key is needed, but its Papers Past coverage was not confirmed, so it was not implemented. |

The app never queries several providers at once, never bypasses logins, paywalls or CAPTCHAs, and does not treat free viewing as permission to bulk-download.

### AI providers

- **Adapters.** OpenAI uses the Responses API via `openai` 3.24; Anthropic uses the Messages API via `anthropic` 1.11. Both sit behind one task interface.
- **Model discovery** uses each provider's model-list endpoint.
  - Anthropic reports capabilities: structured output, image and PDF input, effort levels, context size.
  - OpenAI does not, so the app shows "not reported" and checks at run time.
- **What's tested.** Error handling, cancellation, the duplicate-submission guard, the "no silent fallback" rule and privacy gates are covered by automated tests with **mocked** clients.
- **What isn't.** I did not make live AI calls, because no API key was available in this session. Use **AI Settings → Check connection** (lists models; no text generation) and **Send test prompt** (≤16 output tokens; may incur a small charge) to verify your own keys.
- **Cost** is always shown as "unknown". Neither provider publishes machine-readable pricing, and the app does not hardcode prices.

Five AI tasks are available, each with an optional provider/model override:
- research planning
- query expansion and multilingual variants
- transcription and extraction
- evidence comparison
- summarization

Before every run the app shows the exact provider and model, what data will be sent, compatibility problems, and whether fallback is enabled. Then:
- Possibly-living people and attachments are blocked unless you allow them.
- Supplied documents are wrapped as untrusted data.
- "Extracted" facts must quote the source; facts whose quote isn't found in the text are downgraded to "inference".
- Results become proposals; nothing changes until you accept one.
- Cross-provider fallback is off unless you enable it, and it is recorded on the run.

## Directory coverage and what still needs verification

The seed was checked against provider pages on **2026-10-05**: 51 entries verified, 27 partly verified, 6 needing verification. **Coverage is a starting set, not a complete list.** Local repositories in particular are an initial sample (about 25), and international coverage is limited to the countries named in the brief.

**Needs verification.** The sites blocked automated checks, so these entries make no coverage or access claims:
- MyHeritage records search (access is taken from a help article only)
- IrishGenealogy.ie
- Massachusetts Archives
- masslandrecords.com
- Cook County Clerk genealogy
- NYPL Milstein Division

**Partly verified** (see each entry's maintenance notes):
- **FamilySearch:** Full-Text Search and Catalog (results require sign-in).
- **U.S. federal and national:** 1950 Census site, American Ancestors (whether search is free is unconfirmed), LOC genealogy guides, Indian Census Rolls guide (date range differs between sources), Ellis Island Foundation search.
- **UK and Ireland:** TNA guides, ScotlandsPeople, National Archives of Ireland census search.
- **Canada:** Library and Archives Canada, Archives of Ontario, BAnQ.
- **Australia and New Zealand:** Trove (URL pattern not verified because of a bot check), PROV Victoria, National Library of NZ, Archives NZ.
- **Other international:** Geneanet, JewishGen.
- **U.S. local and state:** Pennsylvania State Archives, Ohio History Connection, California State Archives, Worcester Probate & Family Court, Allen County Genealogy Center, Historical Society of Pennsylvania, American Jewish Archives, Council of State Archivists directory.

**Notable changes found during verification:**
- The legacy Chronicling America API was retired in 2025.
- BLM moved GLO Records to a new portal on 2026-07-13; old deep links no longer work.
- DPLA is now maintained by Cleveland Public Library.
- The Moravian Archives reported broken online finding aids from 2026-09-30.

## Using it — the core workflow

1. **Import your tree.** Use More → Import a tree, with an Ancestry or other GEDCOM export. Alternatively, add people under **People**.
2. **Home** shows the most useful next steps. Choose a **home person** on the Family tree page; suggestions follow their direct line first.
3. **Open a person.** In the **Record checklist**:
   - **FamilySearch / Ancestry** buttons open that site's search for the right collection, with name, birth years, birthplace and residence filled in. If nothing turns up, **"If it isn't found"** offers variant searches.
   - **Search now** runs a free search the app can do itself (the 1950 census, the Irish census, newspapers) and checks every result.
   - **Research automatically** runs all the searches that apply to the person in one go.
4. **Leads** asks one question per result: *is this the right person?* Each lead shows:
   - what fits and what doesn't (ages, titles, places and relatives *next to the name*, dates);
   - **new names to look into:** people with the family surname named next to your person who aren't in your tree yet.

   Answer **Yes**, **Not them** or **Not sure**. "Yes" saves it as a source; you can link it to a specific fact later.
5. **Edit facts & sources** on a person page opens the detailed claim and evidence editor:
   - Conflicting claims are kept side by side.
   - Confirming a claim requires supporting evidence.
   - Contributed trees and cemetery memorials alone are never treated as proof.

How matching avoids false matches and missed records is described in [docs/research-runs.md](docs/research-runs.md#how-results-are-checked).

The **🧪 Demo** project is fictional, clearly labelled, and separate from your data. You can reset or delete it in Settings.

## Tests

```bash
.venv/bin/python -m pytest -q
```

119 tests cover:
- directory filtering: geography, dates, access, record type, unknown coverage, partial overlap, known gaps
- deterministic recommendations and explanations
- negative-search history and alternatives
- claims, citations, supporting/contradicting evidence and conflict flags
- seed updates preserving user edits
- persistence across restarts
- full and project export/import
- backup/restore including attachments, plus rejection of tampered and unsafe archives
- CSV injection
- attachment safety: type allow-list, magic bytes, path traversal
- CSRF and host checks
- input validation
- the AI subsystem with mocked providers: config persistence, model refresh and caching, manual validation, task and per-run overrides, incompatible capabilities, normalised failures, no silent fallback, cancellation, duplicate guard, consent and living-person privacy, extracted vs. inferred facts
- a full 11-step end-to-end workflow
- research runs: planning, scoring with full text, same-name traps (from a live run), auto-saving as unreviewed, review actions, reruns, logging negatives, keys, provider caching limits; key-based adapter request/response mapping; the AI research assistant with scripted Anthropic and OpenAI clients (tool calls, quote verification, web-URL grounding, budgets, consent and living-person blocks, prompt-injection text)
- GEDCOM import: Ancestry-style, Family Tree Maker (with media folder) and ANSEL-encoded RootsMagic exports; ZIP-wrapped exports; uncertain and dual dates; multiple marriages; adopted/step relationships; Unicode names; custom tags; parse failures; missing, ambiguous and remote media; repeat imports without duplicates, including reused identifiers; local edits preserved; review decisions; undo; ZIP-slip, symlink and ZIP-bomb protection

I also checked the UI by hand in a browser: desktop and 375px widths, the mobile menu, dialog keyboard focus and Escape, and the live Chronicling America search.

## Known limitations

- **The directory is incomplete** and will drift. Re-verify entries periodically; provider access terms and URLs change.
- **Coverage matching is only as good as the metadata.** Many entries have no recorded date ranges and show as "coverage unknown". Geographic matching uses names, not a gazetteer, so historical boundary changes are recorded only as free-text "historical jurisdiction".
- **Only one implemented retrieval integration** (Chronicling America). All other providers are outbound links.
- **AI adapters were tested with mocks only** in this build. OpenAI capabilities can only be confirmed at run time. PDF input is sent to Anthropic only (OpenAI gets images only).
- **Single-user and local:** no sync, no multi-device, no user accounts. Run it on one machine and use backups to move data.
- **Relationship conflicts:** only simple checks (more than two proposed parents; differing single-event dates or places).
- **No timeline, map, or GEDCOM *export* yet.** GEDCOM import is available.
- **The research pathways** (African American, Indigenous, adoption, displacement, migration) summarise guidance pages checked on 2026-10-05. They are starting points, not complete guides, and the adoption-law summary they cite is itself only current to 2019.

## Project layout

```
app/            FastAPI backend
  main.py       app factory, security middleware (localhost-only, CSRF header, CSP)
  routes.py     directory, workspace, evidence, log, data portability endpoints
  routes_ai.py  AI settings, models, previews, runs, proposals
  directory.py coverage.py recommend.py names.py dates.py taxonomy.py
  workspace.py research_log.py evidence.py attachments.py portability.py seeding.py demo.py
  gedcom/       GEDCOM parser (encodings incl. ANSEL), mapping, media matching, import lifecycle
  routes_import.py  import endpoints
  ai/           credentials (keychain), providers (OpenAI/Anthropic adapters), tasks, service
  integrations/ adapter interface + Library of Congress adapter + verified link builder
  migrations/   numbered SQL migrations
  seed/         versioned directory seed
static/         UI (Preact + htm, no build), styles
tools/          seed builder + raw verification findings
tests/          pytest suite
```
