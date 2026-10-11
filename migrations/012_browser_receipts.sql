-- Browser-observed receipt information is NOT an employer-signed confirmation.
-- It must not increment the independently verified submitted application counter.
CREATE TABLE IF NOT EXISTS smartploy_browser_receipts (
    profile_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL REFERENCES smartploy_application_workspaces(workspace_id) ON DELETE CASCADE,
    document_revision INTEGER NOT NULL CHECK (document_revision > 0),
    document_sha256 CHAR(64) NOT NULL,
    reference TEXT NOT NULL CHECK (char_length(reference) BETWEEN 4 AND 64),
    confirmation_page_url TEXT NOT NULL CHECK (char_length(confirmation_page_url) <= 1500),
    confirmation_page_sha256 CHAR(64) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    evidence_digest CHAR(64) NOT NULL,
    status TEXT NOT NULL DEFAULT 'browser_observed_unverified'
        CHECK (status = 'browser_observed_unverified'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, workspace_id)
);
CREATE INDEX IF NOT EXISTS smartploy_browser_receipts_observed_at_idx
    ON smartploy_browser_receipts (profile_id, observed_at DESC);
