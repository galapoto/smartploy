CREATE TABLE IF NOT EXISTS smartploy_application_artifacts (
    artifact_id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL REFERENCES smartploy_application_preparations(package_id) ON DELETE RESTRICT,
    canonical_key TEXT NOT NULL REFERENCES smartploy_jobs(canonical_key) ON DELETE RESTRICT,
    artifact_type TEXT NOT NULL CHECK (
        artifact_type IN ('cv_docx','cv_pdf','cover_letter_docx','cover_letter_pdf')
    ),
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 5242880),
    content BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS smartploy_application_artifacts_package_idx
    ON smartploy_application_artifacts (package_id, artifact_type, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS smartploy_application_artifacts_content_idx
    ON smartploy_application_artifacts (package_id, artifact_type, content_sha256);
