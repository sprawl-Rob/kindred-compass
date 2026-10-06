-- Kindred Compass schema v2: GEDCOM / Ancestry import

-- Where a record came from (user-entered, imported, AI-accepted). Imported claims are never "verified".
ALTER TABLE persons ADD COLUMN origin TEXT NOT NULL DEFAULT 'user';
ALTER TABLE claims ADD COLUMN origin TEXT NOT NULL DEFAULT 'user';
ALTER TABLE claims ADD COLUMN relationship_qualifier TEXT;   -- biological | adopted | step | foster | guardian | sealed | unknown | other
ALTER TABLE sources ADD COLUMN origin TEXT NOT NULL DEFAULT 'user';
ALTER TABLE person_names ADD COLUMN origin TEXT NOT NULL DEFAULT 'user';
ALTER TABLE projects ADD COLUMN import_lineage_id TEXT;

-- One lineage per originating tree. Source identifiers (xrefs, _UID, RIN) are only meaningful inside a lineage.
CREATE TABLE import_lineages (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    product       TEXT NOT NULL,           -- ancestry | ftm | rootsmagic | other
    tree_label    TEXT,                    -- tree name as given in the file header
    tree_key      TEXT NOT NULL,           -- product + tree id/name (used to suggest the lineage on repeat imports)
    created_at    TEXT NOT NULL
);

CREATE TABLE import_batches (
    id                TEXT PRIMARY KEY,
    lineage_id        TEXT REFERENCES import_lineages(id) ON DELETE SET NULL,
    project_id        TEXT REFERENCES projects(id) ON DELETE SET NULL,
    status            TEXT NOT NULL,       -- previewed | committed | undone | failed | discarded
    original_filename TEXT NOT NULL,
    stored_dir        TEXT NOT NULL,       -- relative to data/imports
    gedcom_member     TEXT,                -- file name inside a ZIP, if any
    sha256            TEXT NOT NULL,
    product           TEXT,
    gedcom_version    TEXT,
    encoding          TEXT,
    detection_json    TEXT NOT NULL DEFAULT '{}',
    plan_json         TEXT NOT NULL DEFAULT '{}',   -- preview: counts, warnings, unsupported, profiles, match plan
    report_json       TEXT NOT NULL DEFAULT '{}',   -- after commit
    media_json        TEXT NOT NULL DEFAULT '{}',   -- supplied media inventory
    created_project   INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    committed_at      TEXT,
    undone_at         TEXT
);

-- Each GEDCOM record seen in a lineage (INDI, FAM, SOUR, REPO, OBJE, NOTE), with its original lines.
CREATE TABLE import_records (
    id              TEXT PRIMARY KEY,
    lineage_id      TEXT NOT NULL REFERENCES import_lineages(id) ON DELETE CASCADE,
    record_type     TEXT NOT NULL,
    xref            TEXT,
    stable_keys_json TEXT NOT NULL DEFAULT '[]',   -- e.g. ["_UID:ABC…", "RIN:12"] — scoped to this lineage
    entity_type     TEXT,                           -- person | source | ...
    entity_id       TEXT,
    content_hash    TEXT NOT NULL,
    raw_json        TEXT NOT NULL,                  -- the record subtree (tag, value, line numbers, children)
    first_batch_id  TEXT NOT NULL,
    last_batch_id   TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX idx_import_records_lineage ON import_records(lineage_id, record_type, xref);

-- Links from every created research row back to the exact GEDCOM lines it came from (side-by-side view).
CREATE TABLE import_links (
    id            TEXT PRIMARY KEY,
    batch_id      TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    lineage_id    TEXT NOT NULL,
    entity_type   TEXT NOT NULL,       -- person | name | claim | source | attachment | place
    entity_id     TEXT NOT NULL,
    record_xref   TEXT,
    fact_key      TEXT,                -- fingerprint used to avoid duplicate facts on repeat imports
    gedcom_json   TEXT NOT NULL,       -- the original node(s), with line numbers
    imported_at   TEXT NOT NULL,       -- compared with the entity's updated_at to detect local edits
    created       INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_import_links_entity ON import_links(entity_type, entity_id);
CREATE INDEX idx_import_links_fact ON import_links(lineage_id, record_xref, fact_key);

-- Changes made to existing rows by a repeat import (for undo).
CREATE TABLE import_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    table_name  TEXT NOT NULL,
    row_id      TEXT NOT NULL,
    before_json TEXT,                  -- NULL = row was inserted by this batch
    created_at  TEXT NOT NULL
);

CREATE TABLE import_media (
    id            TEXT PRIMARY KEY,
    batch_id      TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    record_xref   TEXT,                -- OBJE xref or owner xref for inline OBJE
    owner_xref    TEXT,
    owner_type    TEXT,                -- person | source | family | none
    file_ref      TEXT,                -- FILE value exactly as written
    title         TEXT,
    form          TEXT,
    kind          TEXT NOT NULL,       -- local | remote
    status        TEXT NOT NULL,       -- matched | missing | ambiguous | remote_not_fetched | unsupported_type | not_supplied
    matched_path  TEXT,
    candidates_json TEXT NOT NULL DEFAULT '[]',
    attachment_id TEXT,
    note          TEXT
);

CREATE TABLE import_review_items (
    id           TEXT PRIMARY KEY,
    batch_id     TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,        -- uncertain_match | conflicting_change | removed_in_source | ambiguous_media
    record_xref  TEXT,
    entity_type  TEXT,
    entity_id    TEXT,
    summary      TEXT NOT NULL,
    detail_json  TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending | accepted | rejected | resolved
    resolution   TEXT,
    created_at   TEXT NOT NULL,
    decided_at   TEXT
);
