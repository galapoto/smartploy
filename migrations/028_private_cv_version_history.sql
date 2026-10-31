-- SP79: bounded owner-private archived source CV / edited versions.
-- Owner-private CV revisions are always queried with the verified profile_id.
CREATE TABLE IF NOT EXISTS smartploy_cv_history (
    profile_id text NOT NULL,
    sha256 char(64) NOT NULL,
    filename text NOT NULL CHECK (char_length(filename) BETWEEN 1 AND 160),
    media_type text NOT NULL CHECK (
      media_type IN (
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      )
    ),
    content bytea NOT NULL CHECK (octet_length(content) <= 5242880),
    extracted_text text NOT NULL CHECK (char_length(extracted_text) <= 60000),
    source_updated_at timestamptz NOT NULL,
    archived_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, sha256)
);
CREATE INDEX IF NOT EXISTS smartploy_cv_history_profile_idx
    ON smartploy_cv_history (profile_id, archived_at DESC);
