CREATE INDEX IF NOT EXISTS smartploy_source_observations_external_id_idx
    ON smartploy_source_observations (source_id, source_external_id, observed_at DESC)
    WHERE source_external_id <> '';
