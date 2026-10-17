-- Account erasure quarantine and unresolved off-platform processor obligations.
-- No CV, email, job description, profile evidence or raw prompt is stored.
-- This migration does NOT authorize remote delete, local hard purge, or new AI.
CREATE TABLE IF NOT EXISTS smartploy_account_erasure_requests (
    request_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    profile_id TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL DEFAULT 'quarantined'
        CHECK (state = 'quarantined'),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (char_length(request_id) BETWEEN 1 AND 80),
    CHECK (char_length(user_id) BETWEEN 1 AND 128),
    CHECK (char_length(profile_id) BETWEEN 1 AND 160)
);

-- Each known remote provider ID or durable request ID requires separate
-- processing, e.g. verified deletion/retention decision, before hard purge.
-- No automatic external deletes and no "verified" claim without evidence.
CREATE TABLE IF NOT EXISTS smartploy_obumai_erasure_obligations (
    obligation_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL
        REFERENCES smartploy_account_erasure_requests(request_id) ON DELETE RESTRICT,
    remote_job_id TEXT NOT NULL DEFAULT '',
    remote_request_id TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'requires_provider_followup'
        CHECK (state = 'requires_provider_followup'),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (remote_job_id <> '' OR remote_request_id <> ''),
    CHECK (char_length(remote_job_id) <= 4096),
    CHECK (char_length(remote_request_id) <= 4096)
);

CREATE INDEX IF NOT EXISTS smartploy_obumai_erasure_obligations_request_idx
    ON smartploy_obumai_erasure_obligations
    (request_id, detected_at DESC, obligation_id);
