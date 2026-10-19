-- SP15f adds official Lever partner API as a DISTINCT, employer-approved channel.
-- Never infer posting-API permission from job discovery or browser-submit rights.
ALTER TABLE smartploy_employer_automation_rights
    DROP CONSTRAINT IF EXISTS smartploy_employer_automation_rights_action_scope_check;
ALTER TABLE smartploy_employer_automation_rights
    ADD CONSTRAINT smartploy_employer_automation_rights_action_scope_check
    CHECK (action_scope IN (
        'single_user_initiated_browser_final_submit',
        'partner_lever_postings_api_submit'
    ));

ALTER TABLE smartploy_employer_final_approvals
    ADD COLUMN IF NOT EXISTS action_scope TEXT NOT NULL
        DEFAULT 'single_user_initiated_browser_final_submit';
ALTER TABLE smartploy_employer_final_approvals
    ADD CONSTRAINT smartploy_employer_final_approvals_action_scope_check
    CHECK (action_scope IN (
        'single_user_initiated_browser_final_submit',
        'partner_lever_postings_api_submit'
    ));

-- A provider-returned application ID is stronger evidence than a local
-- click marker. Do not call it employer hiring acceptance.
CREATE TABLE IF NOT EXISTS smartploy_partner_application_receipts (
    claim_id TEXT PRIMARY KEY
        REFERENCES smartploy_employer_submit_claims (claim_id),
    user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    employer_job_key_sha256 TEXT NOT NULL CHECK (length(employer_job_key_sha256)=64),
    provider TEXT NOT NULL CHECK (provider='lever'),
    provider_application_id TEXT NOT NULL
        CHECK (length(provider_application_id) BETWEEN 8 AND 160),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id,profile_id,employer_job_key_sha256),
    UNIQUE(provider,provider_application_id)
);
CREATE INDEX IF NOT EXISTS smartploy_partner_application_receipts_owner_idx
  ON smartploy_partner_application_receipts (user_id,profile_id,received_at DESC);
