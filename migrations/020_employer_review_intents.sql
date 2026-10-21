-- SP15c expiring final-review record and NO browser actuation capability
-- Reuse SP15a owner lock and immutable employer job identity
-- No resume, email, raw employer URL, account credential, bearer secret or answer
CREATE TABLE IF NOT EXISTS smartploy_employer_review_intents (
    intent_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    employer_job_key_sha256 TEXT NOT NULL CHECK (length(employer_job_key_sha256)=64),
    workspace_id TEXT NOT NULL,
    document_revision INTEGER NOT NULL CHECK (document_revision>0),
    document_sha256 TEXT NOT NULL CHECK (length(document_sha256)=64),
    cv_pdf_sha256 TEXT NOT NULL CHECK (length(cv_pdf_sha256)=64),
    state TEXT NOT NULL CHECK (state IN ('pending','cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(intent_id) BETWEEN 1 AND 128),
    CHECK (expires_at>created_at),
    UNIQUE (user_id,profile_id,employer_job_key_sha256)
);
CREATE INDEX IF NOT EXISTS smartploy_employer_review_intents_expiry_idx
    ON smartploy_employer_review_intents (expires_at,state);
CREATE INDEX IF NOT EXISTS smartploy_employer_review_intents_owner_idx
    ON smartploy_employer_review_intents (user_id,profile_id);
