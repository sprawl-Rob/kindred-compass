-- AI-assisted reading of imported documents: the latest AI reading and the run that produced it.
ALTER TABLE documents ADD COLUMN ai_json TEXT;
ALTER TABLE documents ADD COLUMN ai_run_id TEXT;
