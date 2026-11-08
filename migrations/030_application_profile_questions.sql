-- SP116: durable, owner-private memory of safe ATS questions and applicant-reviewed
-- reusable answers. Separate from approved career facts, AI prompts and send grants.
CREATE TABLE IF NOT EXISTS smartploy_application_profile_questions (
    profile_id TEXT NOT NULL,
    question_key TEXT NOT NULL,
    label TEXT NOT NULL CHECK (char_length(label) BETWEEN 3 AND 150),
    answer TEXT NOT NULL DEFAULT '' CHECK (char_length(answer) <= 1500),
    approved_for_reuse BOOLEAN NOT NULL DEFAULT FALSE,
    reusable_scope TEXT NOT NULL DEFAULT 'exact_question'
        CHECK (reusable_scope IN ('exact_question','manual_only')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, question_key),
    CONSTRAINT smartploy_question_key_format
        CHECK (question_key ~ '^[a-f0-9]{64}$'),
    CONSTRAINT smartploy_question_approval_requires_answer
        CHECK (NOT approved_for_reuse OR (char_length(btrim(answer)) >= 2
          AND reusable_scope = 'exact_question'))
);
CREATE INDEX IF NOT EXISTS smartploy_app_profile_questions_review_idx
  ON smartploy_application_profile_questions
  (profile_id, approved_for_reuse, updated_at DESC);

-- CV-only is an explicit opt-in, persisted per signed-in account.
CREATE TABLE IF NOT EXISTS smartploy_application_profile_settings (
  profile_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL DEFAULT 'guided' CHECK (mode IN ('guided','cv_only')),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
