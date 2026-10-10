CREATE TABLE IF NOT EXISTS smartploy_application_preparations (
    package_id TEXT PRIMARY KEY,
    canonical_key TEXT NOT NULL REFERENCES smartploy_jobs(canonical_key) ON DELETE RESTRICT,
    profile_id TEXT NOT NULL,
    preparation_contract TEXT NOT NULL,
    job_snapshot_sha256 TEXT NOT NULL CHECK (length(job_snapshot_sha256) = 64),
    evidence_sha256 TEXT NOT NULL CHECK (length(evidence_sha256) = 64),
    score_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (
        status IN (
            'created','queued','running','blocked','completed',
            'completed_unparsed','failed','cancelled'
        )
    ),
    obum_job_id TEXT NOT NULL DEFAULT '',
    obum_client_request_id TEXT NOT NULL DEFAULT '',
    requested_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_output TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS smartploy_application_preparations_job_idx
    ON smartploy_application_preparations (canonical_key, requested_at DESC);

CREATE INDEX IF NOT EXISTS smartploy_application_preparations_state_idx
    ON smartploy_application_preparations (status, requested_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS smartploy_application_preparations_obum_request_idx
    ON smartploy_application_preparations (obum_client_request_id)
    WHERE obum_client_request_id <> '';
