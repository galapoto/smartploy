-- SP15e independent, operator-reviewed employer final-action rights.
-- Existing job-acquisition SourcePolicy approval NEVER authorizes employer submit.
-- No public rights-write API. Without independently attested rows, FAIL CLOSED.
CREATE TABLE IF NOT EXISTS smartploy_employer_automation_rights (
    employer_job_key_sha256 TEXT PRIMARY KEY CHECK (length(employer_job_key_sha256)=64),
    action_scope TEXT NOT NULL DEFAULT 'single_user_initiated_browser_final_submit'
        CHECK (action_scope='single_user_initiated_browser_final_submit'),
    permission_basis TEXT NOT NULL
        CHECK (permission_basis IN (
            'explicit_employer_authorization','documented_partner_integration'
        )),
    permission_evidence_sha256 TEXT NOT NULL CHECK (length(permission_evidence_sha256)=64),
    terms_evidence_sha256 TEXT NOT NULL CHECK (length(terms_evidence_sha256)=64),
    reviewed_by TEXT NOT NULL CHECK (length(reviewed_by) BETWEEN 8 AND 128),
    independently_approved_by TEXT NOT NULL
        CHECK (length(independently_approved_by) BETWEEN 8 AND 128),
    reviewed_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('approved','revoked')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (reviewed_by <> independently_approved_by),
    CHECK (expires_at > reviewed_at),
    CHECK (expires_at <= reviewed_at + interval '90 days')
);
CREATE INDEX IF NOT EXISTS smartploy_employer_rights_expiry_idx
    ON smartploy_employer_automation_rights (state,expires_at);

-- Stored final user action approval is NOT a token or employer click.
-- One active/used approval per verified owner and actual Lever employer job.
CREATE TABLE IF NOT EXISTS smartploy_employer_final_approvals (
    approval_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    employer_job_key_sha256 TEXT NOT NULL CHECK (length(employer_job_key_sha256)=64),
    workspace_id TEXT NOT NULL,
    document_revision INTEGER NOT NULL CHECK (document_revision>0),
    document_sha256 TEXT NOT NULL CHECK (length(document_sha256)=64),
    cv_pdf_sha256 TEXT NOT NULL CHECK (length(cv_pdf_sha256)=64),
    approved_fields_sha256 TEXT NOT NULL CHECK (length(approved_fields_sha256)=64),
    application_url_sha256 TEXT NOT NULL CHECK (length(application_url_sha256)=64),
    permission_evidence_sha256 TEXT NOT NULL CHECK (length(permission_evidence_sha256)=64),
    state TEXT NOT NULL CHECK (state IN ('approved','cancelled','consumed_unverified')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(approval_id) BETWEEN 1 AND 128),
    CHECK (expires_at>created_at),
    UNIQUE(user_id,profile_id,employer_job_key_sha256)
);
CREATE INDEX IF NOT EXISTS smartploy_employer_final_approvals_owner_idx
    ON smartploy_employer_final_approvals (user_id,profile_id,updated_at DESC);
