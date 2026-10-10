CREATE TABLE IF NOT EXISTS smartploy_profile_facts (
    profile_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    source TEXT NOT NULL,
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, fact_id)
);

CREATE INDEX IF NOT EXISTS smartploy_profile_facts_approved_type_idx
    ON smartploy_profile_facts (profile_id, approved, fact_type);
