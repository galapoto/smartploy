-- SP25: reconcile application-submission truth into an existing durable case.
-- Reentrant: backfill only when the new column is absent on an existing row.
-- Never reset a previously observed status on subsequent deployments.
ALTER TABLE smartploy_application_agents
  ADD COLUMN IF NOT EXISTS observed_workspace_status TEXT;

UPDATE smartploy_application_agents a
   SET observed_workspace_status = w.status
  FROM smartploy_application_workspaces w
 WHERE w.workspace_id = a.workspace_id
   AND w.profile_id = a.profile_id
   AND a.observed_workspace_status IS NULL;

ALTER TABLE smartploy_application_agents
  ALTER COLUMN observed_workspace_status SET DEFAULT 'draft';
ALTER TABLE smartploy_application_agents
  ALTER COLUMN observed_workspace_status SET NOT NULL;

ALTER TABLE smartploy_application_agents
  DROP CONSTRAINT IF EXISTS smartploy_application_agents_observed_workspace_status_check;
ALTER TABLE smartploy_application_agents
  ADD CONSTRAINT smartploy_application_agents_observed_workspace_status_check
    CHECK (observed_workspace_status IN (
      'draft', 'self_reported_applied', 'provider_acknowledged'
    ));

ALTER TABLE smartploy_application_agent_events
  DROP CONSTRAINT IF EXISTS smartploy_application_agent_events_event_type_check;
ALTER TABLE smartploy_application_agent_events
  ADD CONSTRAINT smartploy_application_agent_events_event_type_check
    CHECK (event_type IN (
      'case_created','review_reminder_due','case_paused','case_resumed','case_closed',
      'followup_due','candidate_reported_followup',
      'candidate_reported_reply','candidate_reported_interview',
      'candidate_reported_offer','candidate_reported_rejected','candidate_reported_hired',
      'application_self_reported','application_provider_acknowledged'
    ));
