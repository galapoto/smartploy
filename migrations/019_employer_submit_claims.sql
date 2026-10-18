-- Internal-only one-attempt employer ledger; distinct from ObumAI draft dispatch.
-- Sticky across workspace deletion, CV revision, app restart and browser devices.
-- No private CV, contact, bearer token, application URL or external payload.
CREATE TABLE IF NOT EXISTS smartploy_employer_submit_claims (
    claim_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    document_revision INTEGER NOT NULL CHECK (document_revision > 0),
    document_sha256 TEXT NOT NULL CHECK (length(document_sha256) = 64),
    application_url_sha256 TEXT NOT NULL CHECK (length(application_url_sha256) = 64),
    state TEXT NOT NULL CHECK (state IN ('reserved_unverified','uncertain')),
    failure_code TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(claim_id) BETWEEN 1 AND 128),
    CHECK (length(user_id) BETWEEN 1 AND 128),
    CHECK (length(profile_id) BETWEEN 1 AND 160),
    CHECK (length(canonical_key) BETWEEN 1 AND 256),
    CHECK (length(workspace_id) BETWEEN 1 AND 160),
    CHECK (length(failure_code) <= 64),
    UNIQUE (user_id, profile_id, canonical_key)
);
CREATE INDEX IF NOT EXISTS smartploy_employer_submit_claims_owner_idx
    ON smartploy_employer_submit_claims (user_id, profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS smartploy_employer_submit_claims_reconcile_idx
    ON smartploy_employer_submit_claims (state, updated_at ASC, claim_id ASC);
