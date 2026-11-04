-- SP127: private professional connections. Profiles are opt-in and discoverable
-- only by an exact handle. Never expose applicant CV, login email or provider claims.
CREATE TABLE IF NOT EXISTS smartploy_social_profiles (
  user_id TEXT PRIMARY KEY REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
  handle TEXT NOT NULL UNIQUE
    CHECK (handle ~ '^[a-z][a-z0-9_]{2,23}$'),
  display_name TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 2 AND 60),
  discoverable BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS smartploy_social_follows (
  follower_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
  followed_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (follower_id,followed_id),
  CHECK (follower_id <> followed_id)
);
CREATE INDEX IF NOT EXISTS smartploy_social_follows_reverse_idx
  ON smartploy_social_follows(followed_id,created_at DESC);
CREATE TABLE IF NOT EXISTS smartploy_social_blocks (
  blocker_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
  blocked_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(blocker_id,blocked_id),
  CHECK(blocker_id <> blocked_id)
);
CREATE TABLE IF NOT EXISTS smartploy_social_messages (
  message_id TEXT PRIMARY KEY CHECK(message_id ~ '^msg-[a-f0-9]{32}$'),
  sender_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
  recipient_id TEXT NOT NULL REFERENCES smartploy_users(user_id) ON DELETE CASCADE,
  body TEXT NOT NULL CHECK(char_length(body) BETWEEN 1 AND 2000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK(sender_id <> recipient_id)
);
CREATE INDEX IF NOT EXISTS smartploy_social_messages_sender_recent_idx
  ON smartploy_social_messages(sender_id,created_at DESC);
CREATE INDEX IF NOT EXISTS smartploy_social_messages_recipient_recent_idx
  ON smartploy_social_messages(recipient_id,created_at DESC);
