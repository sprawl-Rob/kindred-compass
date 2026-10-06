-- Kindred Compass schema v3: automated research runs (archive searches and AI research assistant)

CREATE TABLE research_runs (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    person_id     TEXT REFERENCES persons(id) ON DELETE SET NULL,
    question_id   TEXT REFERENCES research_questions(id) ON DELETE SET NULL,
    mode          TEXT NOT NULL,               -- automatic | ai
    status        TEXT NOT NULL,               -- running | completed | cancelled | failed | interrupted
    options_json  TEXT NOT NULL DEFAULT '{}',  -- adapters, limits, auto-save, web search, AI selection
    plan_json     TEXT NOT NULL DEFAULT '[]',  -- planned queries with the reason for each
    progress_json TEXT NOT NULL DEFAULT '{}',
    summary_json  TEXT NOT NULL DEFAULT '{}',
    steps_json    TEXT NOT NULL DEFAULT '[]',  -- AI assistant: transcript of tool calls and notes
    ai_provider   TEXT,
    ai_model      TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    error         TEXT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT
);

CREATE TABLE research_hits (
    id             TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    project_id     TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    person_id      TEXT REFERENCES persons(id) ON DELETE SET NULL,
    adapter        TEXT NOT NULL,              -- adapter key, or web_search
    found_by       TEXT NOT NULL,              -- search | ai | web
    query_text     TEXT,
    item_id        TEXT,
    title          TEXT,
    date_text      TEXT,
    url            TEXT,
    snippet        TEXT,                       -- provider snippet / description
    context        TEXT,                       -- text around the matched name, from the item's own text
    place_text     TEXT,
    collection     TEXT,
    record_kind    TEXT,
    score          INTEGER NOT NULL DEFAULT 0, -- match strength for ordering; not a probability
    strength       TEXT NOT NULL DEFAULT 'weak', -- strong | possible | weak
    reasons_json   TEXT NOT NULL DEFAULT '[]',
    quote          TEXT,                       -- AI findings: quote claimed from the item
    quote_verified INTEGER,                    -- 1 if the quote was found in the fetched text
    status         TEXT NOT NULL DEFAULT 'candidate', -- candidate | auto_saved | saved | maybe | rejected
    source_id      TEXT REFERENCES sources(id) ON DELETE SET NULL,
    dedupe_key     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    decided_at     TEXT
);
CREATE INDEX idx_hits_run ON research_hits(run_id);
CREATE INDEX idx_hits_person ON research_hits(person_id, dedupe_key);

ALTER TABLE research_log ADD COLUMN origin TEXT NOT NULL DEFAULT 'user';   -- user | automatic | ai
ALTER TABLE research_log ADD COLUMN run_id TEXT;
