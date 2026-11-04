-- SP128: private evidence links for user-initiated moderation reports.
-- A report is not a ban or a delivered notification. No CV/email or duplicated
-- message body is stored in this ledger; moderator access is server allowlisted.
CREATE TABLE IF NOT EXISTS smartploy_social_reports (
  report_id TEXT PRIMARY KEY CHECK (report_id ~ '^report-[a-f0-9]{32}$'),
  reporter_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
  reported_user_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
  message_id TEXT NOT NULL REFERENCES smartploy_social_messages(message_id)
    ON DELETE CASCADE,
  reason TEXT NOT NULL CHECK (reason IN
    ('spam','harassment','scam','impersonation','other')),
  note TEXT NOT NULL DEFAULT '' CHECK (char_length(note) <= 500),
  state TEXT NOT NULL DEFAULT 'open'
    CHECK (state IN ('open','reviewed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ,
  reviewed_by TEXT REFERENCES smartploy_users(user_id) ON DELETE SET NULL,
  CHECK (reporter_id <> reported_user_id),
  CHECK ((state='open' AND reviewed_at IS NULL AND reviewed_by IS NULL)
     OR (state='reviewed' AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)),
  UNIQUE (reporter_id,message_id)
);
CREATE INDEX IF NOT EXISTS smartploy_social_reports_open_idx
  ON smartploy_social_reports(state,created_at DESC);
CREATE INDEX IF NOT EXISTS smartploy_social_reports_reporter_idx
  ON smartploy_social_reports(reporter_id,created_at DESC);
CREATE INDEX IF NOT EXISTS smartploy_social_reports_reported_idx
  ON smartploy_social_reports(reported_user_id,created_at DESC);
