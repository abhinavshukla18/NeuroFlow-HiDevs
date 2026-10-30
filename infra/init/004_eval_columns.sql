ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';
CREATE UNIQUE INDEX IF NOT EXISTS evaluations_run_id_key ON evaluations(run_id);