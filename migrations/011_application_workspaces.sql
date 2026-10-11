-- Editable, locally generated application kits. Owner/profile is always resolved from
-- verified Access/OIDC identity; clients cannot supply a profile_id.
-- This table does NOT assert an external employer submission has occurred.
CREATE TABLE IF NOT EXISTS smartploy_application_workspaces (
    workspace_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    role_title TEXT NOT NULL CHECK (char_length(role_title) BETWEEN 1 AND 150),
    company TEXT NOT NULL CHECK (char_length(company) BETWEEN 1 AND 150),
    application_url TEXT NOT NULL DEFAULT '',
    cv_text TEXT NOT NULL CHECK (char_length(cv_text) BETWEEN 1 AND 30000),
    cover_letter_text TEXT NOT NULL CHECK (char_length(cover_letter_text) BETWEEN 1 AND 10000),
    source_cv_sha256 TEXT NOT NULL DEFAULT '',
    approved_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    job_fingerprint TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','self_reported_applied')),
    self_reported_applied_at TIMESTAMPTZ NULL,
    self_reported_reference TEXT NOT NULL DEFAULT ''
        CHECK (char_length(self_reported_reference) <= 250),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(profile_id, canonical_key)
);
CREATE INDEX IF NOT EXISTS smartploy_workspaces_profile_updated_idx
    ON smartploy_application_workspaces (profile_id, updated_at DESC);
