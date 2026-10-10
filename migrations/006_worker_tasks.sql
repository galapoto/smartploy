CREATE TABLE IF NOT EXISTS smartploy_worker_tasks (
    task_id text PRIMARY KEY,
    task_kind text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    cadence_seconds integer NOT NULL CHECK (cadence_seconds > 0),
    next_run_at timestamptz NOT NULL DEFAULT now(),
    lease_owner text NOT NULL DEFAULT '',
    lease_until timestamptz,
    last_started_at timestamptz,
    last_completed_at timestamptz,
    last_status text NOT NULL DEFAULT 'never',
    consecutive_failures integer NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    last_error text NOT NULL DEFAULT '',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS smartploy_worker_tasks_due_idx
    ON smartploy_worker_tasks (enabled, next_run_at, task_id);

CREATE INDEX IF NOT EXISTS smartploy_worker_tasks_lease_idx
    ON smartploy_worker_tasks (lease_until)
    WHERE lease_until IS NOT NULL;
