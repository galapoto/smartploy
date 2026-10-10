CREATE TABLE IF NOT EXISTS smartploy_users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS smartploy_user_identities (
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
    auth_source TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (issuer, subject)
);

CREATE INDEX IF NOT EXISTS smartploy_user_identities_user_idx
    ON smartploy_user_identities (user_id, created_at);

CREATE TABLE IF NOT EXISTS smartploy_user_profiles (
    user_id TEXT PRIMARY KEY REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE smartploy_applications
    ADD COLUMN IF NOT EXISTS profile_id TEXT;

UPDATE smartploy_applications AS app
SET profile_id = prep.profile_id
FROM smartploy_application_preparations AS prep
WHERE app.package_id = prep.package_id
  AND (app.profile_id IS NULL OR app.profile_id = '');

UPDATE smartploy_applications
SET profile_id = 'default'
WHERE profile_id IS NULL OR profile_id = '';

ALTER TABLE smartploy_applications
    ALTER COLUMN profile_id SET NOT NULL;

ALTER TABLE smartploy_applications
    DROP CONSTRAINT IF EXISTS smartploy_applications_canonical_key_key;

CREATE UNIQUE INDEX IF NOT EXISTS smartploy_applications_profile_job_uidx
    ON smartploy_applications (profile_id, canonical_key);

CREATE INDEX IF NOT EXISTS smartploy_applications_profile_state_idx
    ON smartploy_applications (profile_id, state, updated_at DESC);

CREATE INDEX IF NOT EXISTS smartploy_preparations_profile_idx
    ON smartploy_application_preparations (profile_id, requested_at DESC);
