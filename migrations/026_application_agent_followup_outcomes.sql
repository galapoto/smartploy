-- SP23: candidate-reported outcomes and follow-up counts for existing agent cases.
-- All source claims are owner self-reports, never provider verified receipts.
-- Existing Agent Zero lifecycle rows remain intact.
ALTER TABLE smartploy_application_agents
  ADD COLUMN IF NOT EXISTS milestone TEXT NOT NULL DEFAULT 'none';

ALTER TABLE smartploy_application_agents
  ADD COLUMN IF NOT EXISTS followups_sent INTEGER NOT NULL DEFAULT 0;

ALTER TABLE smartploy_application_agents
  ADD COLUMN IF NOT EXISTS last_followup_at TIMESTAMPTZ;

ALTER TABLE smartploy_application_agents
  DROP CONSTRAINT IF EXISTS smartploy_application_agents_milestone_check;

ALTER TABLE smartploy_application_agents
  ADD CONSTRAINT smartploy_application_agents_milestone_check
  CHECK (milestone IN (
    'none','recruiter_replied','interview','offer','rejected','hired'
  ));

ALTER TABLE smartploy_application_agents
  DROP CONSTRAINT IF EXISTS smartploy_application_agents_followups_sent_check;

ALTER TABLE smartploy_application_agents
  ADD CONSTRAINT smartploy_application_agents_followups_sent_check
  CHECK (followups_sent BETWEEN 0 AND 2);

ALTER TABLE smartploy_application_agents
  DROP CONSTRAINT IF EXISTS smartploy_application_agents_close_reason_check;

ALTER TABLE smartploy_application_agents
  ADD CONSTRAINT smartploy_application_agents_close_reason_check
  CHECK (close_reason IN ('','owner_closed','rejected','hired'));

ALTER TABLE smartploy_application_agents
  DROP CONSTRAINT IF EXISTS smartploy_application_agents_terminal_milestone_check;

ALTER TABLE smartploy_application_agents
  ADD CONSTRAINT smartploy_application_agents_terminal_milestone_check
  CHECK (milestone NOT IN ('rejected','hired') OR state='closed');

ALTER TABLE smartploy_application_agent_events
  DROP CONSTRAINT IF EXISTS smartploy_application_agent_events_event_type_check;

ALTER TABLE smartploy_application_agent_events
  ADD CONSTRAINT smartploy_application_agent_events_event_type_check
  CHECK (event_type IN (
    'case_created','review_reminder_due','case_paused','case_resumed','case_closed',
    'followup_due','candidate_reported_followup',
    'candidate_reported_reply','candidate_reported_interview',
    'candidate_reported_offer','candidate_reported_rejected','candidate_reported_hired'
  ));
