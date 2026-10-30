ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;
ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS pipeline_versions (
  pipeline_id UUID NOT NULL REFERENCES pipelines(id) ON DELETE CASCADE,
  version INT NOT NULL,
  config JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (pipeline_id, version)
);

ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS pipeline_version INT;

INSERT INTO pipeline_versions (pipeline_id, version, config)
SELECT id, version, config FROM pipelines
ON CONFLICT DO NOTHING;