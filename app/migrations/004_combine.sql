-- Combining two projects (e.g. a father's tree and a mother's tree) into one, with undo.
CREATE TABLE combine_runs (
    id                TEXT PRIMARY KEY,
    target_project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    source_name       TEXT NOT NULL,
    pairs_json        TEXT NOT NULL DEFAULT '[]',   -- [{source, target}] people confirmed to be the same
    created_json      TEXT NOT NULL DEFAULT '{}',   -- table -> [ids] rows created in the target (for undo)
    stats_json        TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL,
    undone_at         TEXT
);
