-- SP16: explicit per-profile permission for unattended LOCAL application drafts.
-- This is NOT ObumAI processing consent and never grants employer submission.
CREATE TABLE IF NOT EXISTS smartploy_auto_shortlist_settings (
    profile_id TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT false,
    minimum_score SMALLINT NOT NULL DEFAULT 75
        CHECK (minimum_score BETWEEN 70 AND 100),
    max_per_cycle SMALLINT NOT NULL DEFAULT 3
        CHECK (max_per_cycle BETWEEN 1 AND 10),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_run_at TIMESTAMPTZ NULL,
    last_status TEXT NOT NULL DEFAULT 'not_run'
        CHECK (last_status IN ('not_run','ready','needs_preferences','needs_profile')),
    last_created INTEGER NOT NULL DEFAULT 0 CHECK (last_created >= 0),
    last_inspected INTEGER NOT NULL DEFAULT 0 CHECK (last_inspected >= 0)
);
CREATE INDEX IF NOT EXISTS smartploy_auto_shortlist_enabled_idx
    ON smartploy_auto_shortlist_settings (last_run_at ASC NULLS FIRST)
    WHERE enabled = true;
