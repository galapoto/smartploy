-- Owner-scoped, opt-in, NO EMPLOYER/A.I. submission authorization.
-- No personal CV or job content retained in scheduler enrollment.
CREATE TABLE IF NOT EXISTS smartploy_autodraft_settings (
    user_id TEXT PRIMARY KEY REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT false,
    minimum_score INTEGER NOT NULL DEFAULT 75 CHECK (minimum_score BETWEEN 60 AND 100),
    max_per_cycle INTEGER NOT NULL DEFAULT 5 CHECK (max_per_cycle BETWEEN 1 AND 10),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS smartploy_autodraft_settings_enabled_idx
    ON smartploy_autodraft_settings (updated_at,user_id) WHERE enabled=true;
