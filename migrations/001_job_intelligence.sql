CREATE TABLE IF NOT EXISTS smartploy_jobs (
    canonical_key TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    company TEXT NOT NULL,
    role_title TEXT NOT NULL,
    canonical_url TEXT NOT NULL DEFAULT '',
    candidate JSONB NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    posted_at TIMESTAMPTZ NULL,
    last_verified_at TIMESTAMPTZ NULL,
    closed_at TIMESTAMPTZ NULL,
    source_current BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS smartploy_jobs_current_seen_idx
    ON smartploy_jobs (source_current, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS smartploy_jobs_company_role_idx
    ON smartploy_jobs (company, role_title);

CREATE TABLE IF NOT EXISTS smartploy_source_observations (
    observation_id TEXT PRIMARY KEY,
    canonical_key TEXT NOT NULL REFERENCES smartploy_jobs(canonical_key) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    source_mode TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    source_external_id TEXT NOT NULL DEFAULT '',
    raw_sha256 TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    posted_at TIMESTAMPTZ NULL,
    raw_text TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS smartploy_source_observations_job_idx
    ON smartploy_source_observations (canonical_key, observed_at DESC);

CREATE INDEX IF NOT EXISTS smartploy_source_observations_source_idx
    ON smartploy_source_observations (source_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS smartploy_source_health (
    source_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('healthy', 'degraded', 'failed', 'disabled', 'unknown')),
    parser_version TEXT NOT NULL DEFAULT '',
    last_attempt_at TIMESTAMPTZ NULL,
    last_success_at TIMESTAMPTZ NULL,
    last_failure_at TIMESTAMPTZ NULL,
    last_item_count INTEGER NOT NULL DEFAULT 0 CHECK (last_item_count >= 0),
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    last_error TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
