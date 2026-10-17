-- Durable one-shot ObumAI draft dispatch marker per immutable preparation.
-- A sending/uncertain record is never automatically retried.
-- No CV, email, prompt, job text, tokens, browser data or remote payloads.
-- No new foreign keys into legacy tables, to preserve owner recovery/fixture teardown.
CREATE TABLE IF NOT EXISTS smartploy_obumai_dispatch_attempts (
    package_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    consent_id TEXT NOT NULL,
    consent_revision INTEGER NOT NULL CHECK (consent_revision > 0),
    job_snapshot_sha256 TEXT NOT NULL CHECK (length(job_snapshot_sha256) = 64),
    evidence_sha256 TEXT NOT NULL CHECK (length(evidence_sha256) = 64),
    obum_request_id TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (state IN ('sending','acknowledged','uncertain')),
    obum_job_id TEXT NOT NULL DEFAULT '',
    failure_code TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(package_id) BETWEEN 1 AND 255),
    CHECK (length(user_id) BETWEEN 1 AND 128),
    CHECK (length(profile_id) BETWEEN 1 AND 128),
    CHECK (length(canonical_key) BETWEEN 1 AND 256),
    CHECK (length(consent_id) BETWEEN 1 AND 128),
    CHECK (length(obum_request_id) BETWEEN 1 AND 255),
    CHECK (length(obum_job_id) <= 255),
    CHECK (length(failure_code) <= 64),
    CHECK (state <> 'acknowledged' OR obum_job_id <> ''),
    UNIQUE (user_id, profile_id, canonical_key,
            job_snapshot_sha256, evidence_sha256)
);

CREATE INDEX IF NOT EXISTS smartploy_obumai_dispatch_attempts_owner_idx
    ON smartploy_obumai_dispatch_attempts (user_id, profile_id, created_at DESC);

CREATE INDEX IF NOT EXISTS smartploy_obumai_dispatch_attempts_unresolved_idx
    ON smartploy_obumai_dispatch_attempts (state, updated_at ASC, package_id ASC)
    WHERE state IN ('sending','uncertain','acknowledged');
