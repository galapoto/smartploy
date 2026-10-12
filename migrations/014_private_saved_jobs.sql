-- User-saved opportunities are separate from the shared approved ATS source registry.
-- Each read, insert and delete must be scoped to an authenticated profile_id.
-- This is not an employer availability claim or an application submission.
CREATE TABLE IF NOT EXISTS smartploy_private_saved_jobs (
    profile_id TEXT NOT NULL CHECK (char_length(profile_id) BETWEEN 1 AND 160),
    saved_job_id TEXT NOT NULL CHECK (char_length(saved_job_id) BETWEEN 1 AND 48),
    company TEXT NOT NULL CHECK (char_length(company) BETWEEN 1 AND 160),
    role_title TEXT NOT NULL CHECK (char_length(role_title) BETWEEN 1 AND 160),
    description TEXT NOT NULL CHECK (char_length(description) BETWEEN 1 AND 12000),
    location TEXT NOT NULL DEFAULT '' CHECK (char_length(location) <= 160),
    application_url TEXT NOT NULL DEFAULT '' CHECK (char_length(application_url) <= 2048),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, saved_job_id)
);

CREATE INDEX IF NOT EXISTS smartploy_private_saved_jobs_owner_recent_idx
    ON smartploy_private_saved_jobs (profile_id, created_at DESC, saved_job_id DESC);
