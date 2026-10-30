CREATE INDEX IF NOT EXISTS chunks_metadata_gin ON chunks USING gin (metadata jsonb_path_ops);
