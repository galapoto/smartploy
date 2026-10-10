# Worker health checks and release acceptance

## Why the initial deployment marked the worker unhealthy

The API image has an image-level HTTP healthcheck at `127.0.0.1:8090/healthz`.
SmartPloy's worker reuses that image but replaces the command with
`python scripts/source_worker.py`; it does not run the API's HTTP listener.
Without a Compose override Docker reports the worker **unhealthy** even when
its scheduler loop is running.

## The worker-specific probe

The `worker` service overrides the image-level HTTP check with
`python -m smartploy.worker_health`. Every 30 seconds it verifies:

1. `SMARTPLOY_DATABASE_URL` exists inside the worker container;
2. PostgreSQL can be reached within a three-second connection timeout;
3. the `public.smartploy_worker_tasks` scheduling table exists.

The probe has no network listener, does not perform job searches, does not
change any records, and never prints a DSN or the underlying exception.
Docker's container state separately determines whether the foreground worker
process remains running.

**Limit:** this probe verifies scheduler infrastructure availability; it does
not certify each external job feed or that individual jobs succeeded. Operators
should inspect the separately stored task statuses, failures and timestamps.

## Production release gates

The read-only `deploy/personal/scripts/assert-healthy-stack.sh` checks
`postgres`, `api`, `worker` and `web` with Docker's running and health
states, waiting at most roughly two minutes for startup. If any service is
still unhealthy, it fails and prints **status labels only**, not logs or
environment values.

Deployment cannot record its deployed-SHA success marker unless all four
services become healthy. Backup restore cannot report completion until all
four are healthy. Release-evidence generation also requires all four and
records `stack_healthy=true`. CI now exercises this exact condition against
a real PostgreSQL-backed Docker Compose stack.

### Operator update on obum-core-01

After PR validation and merge, run:

```bash
cd /srv/obum/stacks/smartploy
sudo bash deploy/personal/scripts/preflight.sh
sudo bash deploy/personal/scripts/deploy.sh main
sudo bash deploy/personal/scripts/live-acceptance.sh
sudo bash deploy/personal/scripts/release-evidence.sh --online
```

The deployment rebuilds/recreates SmartPloy's application services, backs up
its own database, applies migrations and may briefly interrupt SmartPloy
requests. It does not change the separate ObumAI project. The private
`deploy/personal/env` must not be printed, copied into Git, or regenerated.
Never use `docker compose down -v` on production.

This fix does not enable ObumAI machine access, public ATS job sources,
Cloudflare SSO cutover, or external job application submission.
