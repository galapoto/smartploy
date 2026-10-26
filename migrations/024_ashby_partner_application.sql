-- SP52: distinct Ashby partner action, never a browser-click or Lever key.
-- Reentrant: the real migrations runner replays this in isolated CI.
ALTER TABLE smartploy_employer_automation_rights
    DROP CONSTRAINT IF EXISTS smartploy_employer_automation_rights_action_scope_check;
ALTER TABLE smartploy_employer_automation_rights
    ADD CONSTRAINT smartploy_employer_automation_rights_action_scope_check
    CHECK (action_scope IN (
        'single_user_initiated_browser_final_submit',
        'partner_lever_postings_api_submit',
        'partner_ashby_application_form_submit'
    ));

ALTER TABLE smartploy_employer_final_approvals
    DROP CONSTRAINT IF EXISTS smartploy_employer_final_approvals_action_scope_check;
ALTER TABLE smartploy_employer_final_approvals
    ADD CONSTRAINT smartploy_employer_final_approvals_action_scope_check
    CHECK (action_scope IN (
        'single_user_initiated_browser_final_submit',
        'partner_lever_postings_api_submit',
        'partner_ashby_application_form_submit'
    ));

-- Reuse the original provider acknowledgment table and unique sticky claim.
-- The submitted form reference is NOT the provider's application ID.
ALTER TABLE smartploy_partner_application_receipts
    ADD COLUMN IF NOT EXISTS provider_form_submission_id TEXT NOT NULL DEFAULT '';
ALTER TABLE smartploy_partner_application_receipts
    DROP CONSTRAINT IF EXISTS smartploy_partner_application_receipts_provider_check;
ALTER TABLE smartploy_partner_application_receipts
    ADD CONSTRAINT smartploy_partner_application_receipts_provider_check
    CHECK (provider IN ('lever', 'ashby'));
ALTER TABLE smartploy_partner_application_receipts
    DROP CONSTRAINT IF EXISTS smartploy_partner_application_receipts_ashby_form_check;
ALTER TABLE smartploy_partner_application_receipts
    ADD CONSTRAINT smartploy_partner_application_receipts_ashby_form_check
    CHECK (
        (provider = 'lever' AND provider_form_submission_id = '') OR
        (provider = 'ashby' AND provider_form_submission_id ~*
         '^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
    );
CREATE UNIQUE INDEX IF NOT EXISTS smartploy_partner_ashby_form_id_unique
  ON smartploy_partner_application_receipts(provider,provider_form_submission_id)
  WHERE provider='ashby';
