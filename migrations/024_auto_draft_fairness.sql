-- SP15k: fair, revocable LOCAL application-draft scan on existing preferences.
-- Reuse SP16's least-recently-scanned queue without its second consent table.
ALTER TABLE smartploy_search_preferences
    ADD COLUMN IF NOT EXISTS auto_draft_last_checked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS smartploy_auto_draft_queue_idx
    ON smartploy_search_preferences
       (auto_draft_last_checked_at ASC NULLS FIRST, profile_id)
    WHERE mode = 'personalized'
      AND criteria @> '{"auto_draft_enabled": true}'::jsonb;
