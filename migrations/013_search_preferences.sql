-- Per-account search onboarding. General mode never uses profile facts for ranking.
-- Criteria stay private, separate from approved CV evidence and applications.
CREATE TABLE IF NOT EXISTS smartploy_search_preferences (
    profile_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('general', 'personalized')),
    criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(criteria) = 'object')
);
