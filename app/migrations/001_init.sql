-- Kindred Compass schema v1
-- Conventions: ids are TEXT (uuid4 hex) except settings; JSON columns end in _json;
-- timestamps are ISO-8601 UTC strings; dates the user types are kept verbatim in *_text.

------------------------------------------------------------------
-- Resource directory: providers and their collections are separate
------------------------------------------------------------------
CREATE TABLE providers (
    id              TEXT PRIMARY KEY,
    seed_key        TEXT UNIQUE,              -- stable key from seed data (NULL = user-created)
    name            TEXT NOT NULL,
    homepage_url    TEXT,
    provider_type   TEXT NOT NULL DEFAULT 'other',
    country         TEXT,
    description     TEXT,
    notes           TEXT,
    archived        INTEGER NOT NULL DEFAULT 0,
    origin          TEXT NOT NULL DEFAULT 'user',   -- seed | user
    seed_version    INTEGER,
    seed_hash       TEXT,                     -- hash of seed values last applied
    user_fields_json TEXT NOT NULL DEFAULT '[]', -- fields edited by the user (protected from seed updates)
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE collections (
    id                    TEXT PRIMARY KEY,
    seed_key              TEXT UNIQUE,
    provider_id           TEXT NOT NULL REFERENCES providers(id),
    name                  TEXT NOT NULL,
    url                   TEXT,
    description           TEXT,
    entry_kind            TEXT NOT NULL DEFAULT 'collection', -- collection | search_service | catalog | guide | repository | directory
    repository_type       TEXT,               -- state_archive, county_clerk, probate_court, ...
    geo_scope             TEXT NOT NULL DEFAULT 'unknown',  -- listed | worldwide | unknown
    geo_json              TEXT NOT NULL DEFAULT '[]',  -- [{country, region, county, municipality, historical_jurisdiction, note}]
    dates_json            TEXT NOT NULL DEFAULT '[]',  -- [{from, to, label}]  empty = unknown
    date_gaps_json        TEXT NOT NULL DEFAULT '[]',  -- [{from, to, label}]
    languages_json        TEXT NOT NULL DEFAULT '[]',
    scripts_json          TEXT NOT NULL DEFAULT '[]',
    record_types_json     TEXT NOT NULL DEFAULT '[]',  -- taxonomy keys
    capabilities_json     TEXT NOT NULL DEFAULT '[]',  -- name_index, full_text, catalog, browse_images, onsite, request_only
    evidence_forms_json   TEXT NOT NULL DEFAULT '[]',
    access_search_json    TEXT NOT NULL DEFAULT '["unknown"]',
    access_images_json    TEXT NOT NULL DEFAULT '["unknown"]',
    access_copies_json    TEXT NOT NULL DEFAULT '["unknown"]',
    access_notes          TEXT,
    integration_method    TEXT NOT NULL DEFAULT 'outbound_link', -- outbound_link | verified_search_link | documented_api | licensed_dataset
    search_url            TEXT,               -- page where a user starts a search
    search_url_template   TEXT,               -- only if verified (see search_link_verified)
    search_link_verified  INTEGER NOT NULL DEFAULT 0,
    search_link_notes     TEXT,
    adapter_key           TEXT,               -- implemented integration adapter, if any
    terminology_json      TEXT NOT NULL DEFAULT '[]',
    rights_notes          TEXT,               -- NULL means unknown
    limitations           TEXT,
    digitization_status   TEXT NOT NULL DEFAULT 'unknown',
    verification_status   TEXT NOT NULL DEFAULT 'needs_verification', -- verified | partial | needs_verification | broken
    last_verified         TEXT,
    verification_source   TEXT,
    link_health           TEXT NOT NULL DEFAULT 'unknown', -- ok | redirect | error | unknown
    link_checked_at       TEXT,
    maintenance_notes     TEXT,
    tags_json             TEXT NOT NULL DEFAULT '[]',
    pathways_json         TEXT NOT NULL DEFAULT '[]',
    archived              INTEGER NOT NULL DEFAULT 0,
    origin                TEXT NOT NULL DEFAULT 'user',
    seed_version          INTEGER,
    seed_hash             TEXT,
    user_fields_json      TEXT NOT NULL DEFAULT '[]',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
CREATE INDEX idx_collections_provider ON collections(provider_id);

CREATE TABLE collection_relations (
    id          TEXT PRIMARY KEY,
    a_id        TEXT NOT NULL REFERENCES collections(id),
    b_id        TEXT NOT NULL REFERENCES collections(id),
    relation    TEXT NOT NULL,  -- overlaps | duplicates | indexes_images_of | part_of | successor_of
    note        TEXT,
    origin      TEXT NOT NULL DEFAULT 'user',
    seed_key    TEXT UNIQUE,
    created_at  TEXT NOT NULL
);

-- Change history for directory entries (who/what changed and when)
CREATE TABLE directory_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,  -- provider | collection
    entity_id   TEXT NOT NULL,
    source      TEXT NOT NULL,  -- seed | user | verification
    summary     TEXT,
    diff_json   TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE seed_state (
    name        TEXT PRIMARY KEY,
    version     INTEGER NOT NULL,
    applied_at  TEXT NOT NULL,
    report_json TEXT
);

CREATE TABLE pathways (
    id          TEXT PRIMARY KEY,
    seed_key    TEXT UNIQUE,
    title       TEXT NOT NULL,
    summary     TEXT,
    cautions_json TEXT NOT NULL DEFAULT '[]',
    steps_json  TEXT NOT NULL DEFAULT '[]',
    sources_json TEXT NOT NULL DEFAULT '[]',
    last_verified TEXT,
    verification_status TEXT NOT NULL DEFAULT 'needs_verification',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

------------------------------------------------------------------
-- Research workspace
------------------------------------------------------------------
CREATE TABLE projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    is_demo     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE places (
    id                      TEXT PRIMARY KEY,
    project_id              TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name                    TEXT NOT NULL,       -- as recorded / as the user knows it
    country                 TEXT,
    region                  TEXT,                -- state / province / historic county in UK
    county                  TEXT,
    municipality            TEXT,
    historical_jurisdiction TEXT,                -- e.g. "Prussia, Province of Posen" or "Virginia (before WV statehood)"
    jurisdiction_notes      TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE TABLE persons (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    display_name  TEXT NOT NULL,
    sex           TEXT,                 -- as recorded, optional
    living_status TEXT NOT NULL DEFAULT 'unknown', -- deceased | living | unknown
    is_private    INTEGER NOT NULL DEFAULT 1,
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE person_names (
    id          TEXT PRIMARY KEY,
    person_id   TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    name_type   TEXT NOT NULL DEFAULT 'birth', -- birth | married | maiden | alias | variant | original_script | religious | anglicized
    given       TEXT,
    surname     TEXT,
    full_text   TEXT,
    script      TEXT,
    language    TEXT,
    note        TEXT,
    created_at  TEXT NOT NULL
);

-- Claims: assertions about a person. Conflicting claims coexist; nothing is overwritten.
CREATE TABLE claims (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    person_id         TEXT NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    claim_type        TEXT NOT NULL,    -- birth, baptism, marriage, death, burial, residence, migration, immigration, naturalization, military, occupation, name, relationship, other
    date_text         TEXT,             -- verbatim, e.g. "abt 1852", "bef. Mar 1880"
    date_qualifier    TEXT NOT NULL DEFAULT 'unknown', -- exact | about | before | after | between | estimated | calculated | unknown
    year_from         INTEGER,
    year_to           INTEGER,
    place_id          TEXT REFERENCES places(id) ON DELETE SET NULL,
    to_place_id       TEXT REFERENCES places(id) ON DELETE SET NULL, -- migration destination
    related_person_id TEXT REFERENCES persons(id) ON DELETE SET NULL,
    relationship_type TEXT,             -- parent | child | spouse | sibling | other
    value_text        TEXT,
    statement         TEXT,
    status            TEXT NOT NULL DEFAULT 'working', -- working | tentative | confirmed | disputed | rejected
    status_note       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX idx_claims_person ON claims(person_id);

CREATE TABLE research_questions (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    person_id     TEXT REFERENCES persons(id) ON DELETE SET NULL,
    question      TEXT NOT NULL,
    question_type TEXT NOT NULL DEFAULT 'other',
    year_from     INTEGER,
    year_to       INTEGER,
    place_id      TEXT REFERENCES places(id) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'open',  -- open | answered | on_hold
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE tasks (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    question_id TEXT REFERENCES research_questions(id) ON DELETE SET NULL,
    person_id   TEXT REFERENCES persons(id) ON DELETE SET NULL,
    collection_id TEXT REFERENCES collections(id),
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'todo', -- todo | done
    notes       TEXT,
    origin      TEXT NOT NULL DEFAULT 'user', -- user | recommendation | ai_proposal
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE bookmarks (
    id            TEXT PRIMARY KEY,
    project_id    TEXT REFERENCES projects(id) ON DELETE CASCADE, -- NULL = saved across projects
    collection_id TEXT REFERENCES collections(id),
    url           TEXT,
    title         TEXT,
    note          TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE research_log (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    person_id       TEXT REFERENCES persons(id) ON DELETE SET NULL,
    question_id     TEXT REFERENCES research_questions(id) ON DELETE SET NULL,
    collection_id   TEXT REFERENCES collections(id),
    resource_text   TEXT,          -- free-text resource if not in the directory
    query_text      TEXT NOT NULL DEFAULT '',
    name_variants_json TEXT NOT NULL DEFAULT '[]',
    filters_text    TEXT,
    year_from       INTEGER,
    year_to         INTEGER,
    place_text      TEXT,
    searched_on     TEXT NOT NULL, -- date of search (YYYY-MM-DD)
    coverage_notes  TEXT,
    access_notes    TEXT,
    outcome         TEXT NOT NULL, -- useful | possible_match | no_result | inaccessible | records_unavailable | follow_up
    result_url      TEXT,
    citation_text   TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX idx_log_project ON research_log(project_id);

------------------------------------------------------------------
-- Evidence
------------------------------------------------------------------
CREATE TABLE sources (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title               TEXT NOT NULL,
    creator             TEXT,
    repository          TEXT,
    collection_id       TEXT REFERENCES collections(id),
    collection_name     TEXT,
    record_date_text    TEXT,
    page_ref            TEXT,       -- page / image / folio / entry number
    url                 TEXT,
    accessed_on         TEXT,
    transcription       TEXT,
    excerpt             TEXT,
    record_format       TEXT NOT NULL DEFAULT 'unknown', -- see taxonomy.RECORD_FORMATS
    informant           TEXT,
    informant_knowledge TEXT NOT NULL DEFAULT 'undetermined', -- primary | secondary | undetermined
    citation_text       TEXT,
    research_log_id     TEXT REFERENCES research_log(id) ON DELETE SET NULL,
    duplicate_of_id     TEXT REFERENCES sources(id) ON DELETE SET NULL,
    fingerprint         TEXT,
    provenance_note     TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX idx_sources_fp ON sources(project_id, fingerprint);

CREATE TABLE claim_evidence (
    id                  TEXT PRIMARY KEY,
    claim_id            TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    source_id           TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    stance              TEXT NOT NULL DEFAULT 'supports', -- supports | contradicts | mentions
    identity_match      TEXT NOT NULL DEFAULT 'uncertain', -- certain | probable | possible | uncertain
    assessment          TEXT NOT NULL DEFAULT 'unassessed', -- strong | moderate | weak | unassessed
    interpretation_note TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE (claim_id, source_id)
);

CREATE TABLE attachments (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_type    TEXT NOT NULL,  -- source | log | person
    owner_id      TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_path   TEXT NOT NULL,  -- relative to attachments dir
    mime_type     TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

------------------------------------------------------------------
-- Settings and AI
------------------------------------------------------------------
CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE ai_runs (
    id              TEXT PRIMARY KEY,
    project_id      TEXT REFERENCES projects(id) ON DELETE CASCADE,
    task            TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    status          TEXT NOT NULL,  -- running | succeeded | failed | cancelled
    request_key     TEXT,           -- duplicate-submission guard
    sent_summary_json TEXT NOT NULL DEFAULT '{}', -- what was sent externally
    source_refs_json  TEXT NOT NULL DEFAULT '[]',
    options_json    TEXT NOT NULL DEFAULT '{}',
    output_text     TEXT,
    output_json     TEXT,
    error_code      TEXT,
    error_message   TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_note       TEXT NOT NULL DEFAULT 'unknown',
    fallback_from   TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    duration_ms     INTEGER
);

CREATE TABLE ai_proposals (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES ai_runs(id) ON DELETE CASCADE,
    project_id  TEXT REFERENCES projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,   -- query_variant | research_step | extracted_fact | conflict_note | summary
    payload_json TEXT NOT NULL,
    basis       TEXT NOT NULL DEFAULT 'inference', -- extracted | inference
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    status      TEXT NOT NULL DEFAULT 'pending', -- pending | accepted | rejected
    decided_at  TEXT,
    created_at  TEXT NOT NULL
);
