# Smartploy persistence

Smartploy owns a database separate from ObumAI.

## Modes

- No `SMARTPLOY_DATABASE_URL`: in-memory repository for local development.
- `SMARTPLOY_DATABASE_URL` configured: PostgreSQL repository.

Production should use PostgreSQL.

## Migration

```bash
export SMARTPLOY_DATABASE_URL='postgresql://...'
python scripts/migrate.py
```

The API does not auto-migrate production storage. If PostgreSQL is configured but migration 001 is
missing, `/healthz` reports storage `ready=false`.

## Tables

- `smartploy_jobs`: one canonical current job state per deduplicated vacancy.
- `smartploy_source_observations`: immutable source occurrences/evidence.
- `smartploy_source_health`: connector health across process restarts.

Job upserts preserve the earliest `first_seen_at`, advance `last_seen_at`, keep source occurrence
evidence, and do not create a second canonical job for rediscovery.
