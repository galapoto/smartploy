# Release image provenance — SmartPloy production

## Why a healthy stack can still be stale

An operator's 2026-10-11 deployment log reported a successful release
at `b07d6f0460fc30ab4c229c8681b1200a9cdf581f` and all four services
healthy, but the API, web and worker containers were created around eight
hours before the new image build and their reported image digests differed
from the new build's image digests.

The old release gate checked deployed-sha, HTTP origin health and Docker
health status, but did not bind running image IDs to the images built for
the requested Git SHA. This could incorrectly certify a stale healthy
application.

## Updated deployment contract

`deploy/personal/scripts/deploy.sh` now:

1. Pins Git checkout and builds exact release images:
   `smartploy-api:<sha12>`, `smartploy-web:<sha12>`.
2. Creates a bounded PostgreSQL backup and runs migrations.
3. Force-recreates only the API, worker and web containers with the exact
   newly built images. It does not recreate the Postgres container or
   remove its volume.
4. Waits for all four services to become healthy.
5. Runs `assert-running-images.sh <full-git-sha>`. This compares immutable
   Docker image IDs for API, worker and web to the new release image tags.
6. Records `deployed-sha` only when all checks pass.

Restores now pin the existing trusted deployed SHA, refusing a checkout
mismatch, and avoid the implicit `:dev` tag. They recreate only application
services and verify running image IDs before recording restore success.

Release evidence likewise fails closed if running image IDs do not match
`deployed-sha`; it records `running_release_images_verified=true`.

The image comparison is necessary but not sufficient by itself: production
acceptance still requires private configuration, health, database recovery,
TLS, Cloudflare Access and (separately) authenticated UI verification.

## Read-only host inspection

After a reviewed deployment, run:

```bash
cd /srv/obum/stacks/smartploy
sudo bash deploy/personal/scripts/assert-healthy-stack.sh
SHA="$(sudo git rev-parse HEAD)"
sudo bash deploy/personal/scripts/assert-running-images.sh "$SHA"
sudo bash deploy/personal/scripts/live-acceptance.sh
sudo bash deploy/personal/scripts/release-evidence.sh --online
```

Avoid printing `docker compose config`, container environment variables,
access JWTs, provider keys or private database backups in conversations or CI.

**Do not close go-live issue #57** until these gates pass on-host and the
authenticated frontend/API smoke test is complete. Live job sources and
ObumAI machine integration remain separate activation milestones.
