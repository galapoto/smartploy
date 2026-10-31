-- SP81 binds reviewed contact to the exact signed-in applicant review.
-- Old pending review rows have no contact fingerprint and fail final approval.
ALTER TABLE smartploy_employer_review_intents
    ADD COLUMN IF NOT EXISTS approved_fields_sha256 TEXT NOT NULL DEFAULT '';

ALTER TABLE smartploy_employer_review_intents
    DROP CONSTRAINT IF EXISTS smartploy_reviewed_contact_sha256_check;

ALTER TABLE smartploy_employer_review_intents
    ADD CONSTRAINT smartploy_reviewed_contact_sha256_check
    CHECK (approved_fields_sha256 = ''
           OR approved_fields_sha256 ~ '^[a-f0-9]{64}$');
