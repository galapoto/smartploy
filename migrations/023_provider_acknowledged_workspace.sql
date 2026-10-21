-- SP15h: a real provider-issued application ID is stronger than a user
-- saying "I applied". Preserve the provenance as its OWN state, never turn
-- a provider acknowledgement into a self-reported event.
-- Reentrant because synthetic CI invokes the original migration runner
-- against the same test database repeatedly.
ALTER TABLE smartploy_application_workspaces
    DROP CONSTRAINT IF EXISTS smartploy_application_workspaces_status_check;
ALTER TABLE smartploy_application_workspaces
    ADD CONSTRAINT smartploy_application_workspaces_status_check
    CHECK (status IN ('draft','self_reported_applied','provider_acknowledged'));
