CREATE TABLE IF NOT EXISTS smartploy_sessions (
    session_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    auth_source TEXT NOT NULL DEFAULT 'oidc',
    provider_session_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS smartploy_sessions_user_idx
    ON smartploy_sessions (user_id, expires_at DESC);

CREATE INDEX IF NOT EXISTS smartploy_sessions_provider_sid_idx
    ON smartploy_sessions (issuer, provider_session_id)
    WHERE provider_session_id <> '' AND revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS smartploy_sessions_active_idx
    ON smartploy_sessions (expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS smartploy_oidc_state (
    cache_key_hash TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS smartploy_oidc_state_expiry_idx
    ON smartploy_oidc_state (expires_at);
