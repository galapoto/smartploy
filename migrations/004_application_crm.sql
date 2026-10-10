CREATE TABLE IF NOT EXISTS smartploy_applications (
    application_id TEXT PRIMARY KEY,
    canonical_key TEXT NOT NULL UNIQUE REFERENCES smartploy_jobs(canonical_key) ON DELETE RESTRICT,
    package_id TEXT NOT NULL REFERENCES smartploy_application_preparations(package_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (
        state IN (
            'preparing','ready_for_review','needs_review','preparation_blocked',
            'submitted','acknowledged','recruiter_contact','assessment',
            'interview','offer','rejected','withdrawn'
        )
    ),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    submitted_at TIMESTAMPTZ NULL,
    external_confirmation_id TEXT NOT NULL DEFAULT '',
    external_reference TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS smartploy_applications_state_idx
    ON smartploy_applications (state, updated_at DESC);

CREATE TABLE IF NOT EXISTS smartploy_application_events (
    event_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES smartploy_applications(application_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    from_state TEXT NOT NULL DEFAULT '',
    to_state TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS smartploy_application_events_application_idx
    ON smartploy_application_events (application_id, occurred_at, event_id);
