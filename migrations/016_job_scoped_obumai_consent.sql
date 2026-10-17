-- Job-specific, revocable ObumAI processing consent. Consent alone NEVER starts AI.
-- User/profile binding is re-verified atomically against the identity tables on grant;
-- deliberately no foreign keys to avoid changing existing legacy-owner TRUNCATE flows.
-- Account removal workflows must delete both tables under the privacy retention policy.
CREATE TABLE IF NOT EXISTS smartploy_obumai_consents (
    consent_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    job_snapshot_sha256 TEXT NOT NULL CHECK (length(job_snapshot_sha256) = 64),
    evidence_sha256 TEXT NOT NULL CHECK (length(evidence_sha256) = 64),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, profile_id, canonical_key),
    CHECK (length(user_id) BETWEEN 1 AND 128),
    CHECK (length(profile_id) BETWEEN 1 AND 128),
    CHECK (length(canonical_key) BETWEEN 1 AND 256)
);

CREATE INDEX IF NOT EXISTS smartploy_obumai_consents_owner_idx
    ON smartploy_obumai_consents (user_id, profile_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS smartploy_obumai_consents_active_idx
    ON smartploy_obumai_consents (user_id, profile_id, canonical_key)
    WHERE revoked_at IS NULL;

-- Append-only grant/withdrawal trail stores hashes and metadata, never CV text.
CREATE TABLE IF NOT EXISTS smartploy_obumai_consent_events (
    event_id TEXT PRIMARY KEY,
    consent_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('granted', 'revoked')),
    revision INTEGER NOT NULL CHECK (revision > 0),
    job_snapshot_sha256 TEXT NOT NULL CHECK (length(job_snapshot_sha256) = 64),
    evidence_sha256 TEXT NOT NULL CHECK (length(evidence_sha256) = 64),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS smartploy_obumai_consent_events_owner_idx
    ON smartploy_obumai_consent_events
    (user_id, profile_id, occurred_at DESC, event_id DESC);
