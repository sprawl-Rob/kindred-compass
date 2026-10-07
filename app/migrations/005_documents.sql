-- Imported documents (certificates, letters, photos of records…): the file, its recognised text, and what was found in it.
CREATE TABLE documents (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title           TEXT,
    doc_type        TEXT,                        -- birth | baptism | marriage | death | burial | obituary | letter | naturalization | immigration | military | census | photo | other
    status          TEXT NOT NULL DEFAULT 'processing',   -- processing | ready | failed | attached
    original_name   TEXT NOT NULL,
    attachment_id   TEXT REFERENCES attachments(id) ON DELETE SET NULL,
    pages           INTEGER NOT NULL DEFAULT 1,
    ocr_text        TEXT,                        -- as recognised
    ocr_engine      TEXT,
    ocr_confidence  REAL,
    transcription   TEXT,                        -- as corrected by the user (NULL = use ocr_text)
    detected_json   TEXT NOT NULL DEFAULT '{}',
    error           TEXT,
    source_id       TEXT REFERENCES sources(id) ON DELETE SET NULL,
    person_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX idx_documents_project ON documents(project_id, status);
