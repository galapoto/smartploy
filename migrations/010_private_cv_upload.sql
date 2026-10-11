-- Private CV files are scoped by resolved authenticated profile ID.
-- Raw documents are never available through shared job endpoints.
CREATE TABLE IF NOT EXISTS smartploy_cv_files (
    profile_id text PRIMARY KEY,
    filename text NOT NULL CHECK (char_length(filename) BETWEEN 1 AND 160),
    media_type text NOT NULL CHECK (
      media_type IN (
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      )
    ),
    content bytea NOT NULL CHECK (octet_length(content) <= 5242880),
    extracted_text text NOT NULL CHECK (char_length(extracted_text) <= 60000),
    sha256 char(64) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
