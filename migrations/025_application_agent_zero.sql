-- SP22 Agent Zero: one durable candidate-owned case per existing workspace.
-- No model action, email, browser submit, call or external action is authorized.
-- Workspace deletion cascades through cases and their private timeline.
CREATE TABLE IF NOT EXISTS smartploy_application_agents (
    agent_id TEXT PRIMARY KEY CHECK (char_length(agent_id) BETWEEN 12 AND 80),
    workspace_id TEXT NOT NULL UNIQUE
        REFERENCES smartploy_application_workspaces(workspace_id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL CHECK (char_length(profile_id) BETWEEN 1 AND 160),
    state TEXT NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'paused', 'closed')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    next_due_at TIMESTAMPTZ,
    last_woke_at TIMESTAMPTZ,
    close_reason TEXT NOT NULL DEFAULT ''
        CHECK (close_reason IN ('', 'owner_closed')),
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((state = 'active' AND next_due_at IS NOT NULL AND closed_at IS NULL)
        OR (state = 'paused' AND next_due_at IS NULL AND closed_at IS NULL)
        OR (state = 'closed' AND next_due_at IS NULL AND closed_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS smartploy_application_agent_events (
    agent_id TEXT NOT NULL
        REFERENCES smartploy_application_agents(agent_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    event_type TEXT NOT NULL CHECK (
        event_type IN ('case_created', 'review_reminder_due', 'case_paused',
                       'case_resumed', 'case_closed')
    ),
    message TEXT NOT NULL CHECK (char_length(message) BETWEEN 1 AND 300),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_id, sequence)
);

CREATE INDEX IF NOT EXISTS smartploy_application_agents_owner_idx
    ON smartploy_application_agents (profile_id, updated_at DESC, agent_id);

CREATE INDEX IF NOT EXISTS smartploy_application_agents_due_idx
    ON smartploy_application_agents (next_due_at, agent_id)
    WHERE state = 'active';
