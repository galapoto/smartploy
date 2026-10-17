-- Keep the 60-second status worker efficient as completed history grows.
-- Active records without a remote job ID cannot be polled.
CREATE INDEX IF NOT EXISTS smartploy_preparations_refresh_due_idx
    ON smartploy_application_preparations (updated_at ASC, package_id ASC)
    WHERE status IN ('queued', 'running', 'blocked')
      AND obum_job_id <> '';
