# SmartPloy production stack on obum-core-01

## Host layout

Target repository:

`/srv/obum/stacks/smartploy`

Persistent host paths:

- deployment state: `/srv/obum/data/smartploy/deploy-state`
- backups: `/srv/obum/backups/smartploy`

The Compose stack owns its PostgreSQL volume.

## Runtime topology

```text
Cloudflare
    |
    v
host/shared ingress (Caddy)
    |
    v
127.0.0.1:8091
    |
    v
SmartPloy web gateway (Caddy container)
    |                       |
    | static React          | /api + /healthz
    v                       v
  web/dist              SmartPloy API
                            |
                   +--------+--------+
                   |                 |
               PostgreSQL         ObumAI /
                                  job sources

Continuous worker -> PostgreSQL + approved external sources + bounded ObumAI preparation
```

Only the web gateway is published to the host, and it binds to loopback.

PostgreSQL, API and worker have no host port.

## Initial host setup

Clone the repository to:

~~~bash
sudo install -d /srv/obum/stacks
cd /srv/obum/stacks
git clone https://github.com/galapoto/smartploy.git smartploy
cd smartploy
cp deploy/personal/env.example deploy/personal/env
chmod 600 deploy/personal/env
~~~

Fill `deploy/personal/env` with:
- URL-safe PostgreSQL password;
- SmartPloy Cloudflare Access issuer/audience/approved owner email;
- reviewed ObumAI machine-auth configuration;
- enabled source credentials/configuration.

Do not commit that file.

## Shared host Caddy

The host ingress only needs:

~~~caddy
smartploy.obumai.com {
    reverse_proxy 127.0.0.1:8091
}
~~~

A copy is stored at `deploy/personal/Caddyfile.host.example`.

Cloudflare remains the public DNS/TLS/Access edge. The SmartPloy API independently verifies the Access
application JWT.

## Deploy — immutable approved source (SP30)

After reviewing exact merged-main GitHub CI, native ObumDelivery test evidence
and the independent release approval, the operator selects one full 40-character
commit SHA. Branch names, moving `main`, short SHAs, dirty tracked code, and
commits outside remote main history are rejected before checkout.

~~~bash
cd /srv/obum/stacks/smartploy
SHA=<REVIEWED_FULL_40_CHARACTER_SHA>
sudo env SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc \
  SMARTPLOY_RELEASE_APPROVED_SHA="$SHA" \
  bash deploy/personal/scripts/deploy.sh "$SHA"
~~~

An explicitly reviewed legacy rollback retains the existing Cloudflare
identity profile and uses the same exact-SHA argument. The default identity
profile has NOT been silently switched. Never enable employer submission flags
or partner credentials merely to test a release.

The gate:
1. acquires the original host deployment lock;
2. verifies clean tracked files and ancestry of the exact reviewed commit in origin/main;
3. checks out that exact SHA without `--force` (private untracked env is preserved);
4. validates the immutable identity policy and Compose;
5. builds API/web images and starts PostgreSQL;
6. creates a private backup before database migrations;
7. applies migrations and starts API, worker and web;
8. validates exact running revision, health and image identity;
9. checks real public OIDC origin acceptance when selected;
10. records the deployed SHA only after all required probes pass.

A failed health check does not overwrite the last deployed SHA.
GitHub CI and this source admission gate do not themselves prove native
Woodpecker qualification, an authorized OVH rollout or an employer receipt.

## Backups

Manual backup:

~~~bash
bash deploy/personal/scripts/backup.sh
~~~

Backups:
- use PostgreSQL custom dump format;
- are created with private permissions;
- receive SHA256 sidecar files;
- receive a non-secret metadata sidecar with creation time, dump checksum and source deployed SHA when known;
- coordinate with deploy/restore through the same production-operation lock;
- are stored in `/srv/obum/backups/smartploy` by default;
- retain the newest seven dumps by default.

## Restore

Restore only from a SmartPloy dump that remains inside the configured backup directory:

~~~bash
cd /srv/obum/stacks/smartploy
bash deploy/personal/scripts/restore.sh \
  /srv/obum/backups/smartploy/smartploy-YYYYMMDDTHHMMSSZ-PID.dump
~~~

The restore gate:
1. acquires the same production-operation lock used by deploy/manual backup;
2. rejects symlinks and paths outside the configured backup directory;
3. requires and verifies the SHA256 sidecar;
4. validates backup metadata when present;
5. creates a current-state safety backup without deleting the requested restore artifact;
6. stops API, worker and web before database replacement;
7. restores with clean/if-exists/no-owner/no-privileges/exit-on-error semantics;
8. reruns current migrations;
9. restarts API, worker and web;
10. requires the normal production health contract;
11. records a private restore-evidence file only after health succeeds.

A database restore does **not** overwrite `deployed-sha`; code identity and database recovery identity remain
separate. Restore evidence records the restored dump checksum, source deployed SHA when known, current
code SHA, safety-backup filename and successful health verification.

## Product authority

Deployment does not authorize external job application submission.

The continuous worker may discover/rank jobs and prepare evidence-bound drafts through approved ObumAI
boundaries. Final application submission remains outside this stack's current authority.


## Preflight

Before any production build, migration, backup or deploy action, run:

~~~bash
chmod 600 deploy/personal/env
bash deploy/personal/scripts/preflight.sh
~~~

The preflight is deliberately no-mutation. It verifies host tooling, Docker/Compose availability,
private permissions on the untracked production env, exact committed runtime policy, non-placeholder
database/Cloudflare Access configuration, loopback ingress, absolute backup/state paths, and rendered
Compose least-privilege boundaries.

It reports source and ObumAI integrations only as enabled/disabled and never prints secret values.

To add a reachability-only DNS/HTTPS check:

~~~bash
bash deploy/personal/scripts/preflight.sh --online
~~~

The optional online check is not required for staging or CI.

After containers are running, the separate runtime smoke:

~~~bash
bash deploy/personal/scripts/smoke-env-boundaries.sh
~~~

inspects environment **key names only** inside API, worker, PostgreSQL and web containers. It fails if
source credentials reach the API, Cloudflare identity configuration reaches the worker, or application
secret classes reach PostgreSQL/web.


## Live post-deploy acceptance

After the OVH host route, Cloudflare DNS proxy and Cloudflare Access application are configured, run:

~~~bash
bash deploy/personal/scripts/live-acceptance.sh
~~~

This gate is online but read-only. It first validates the local loopback origin health contract on
`127.0.0.1:<SMARTPLOY_WEB_HOST_PORT>` using the production Host header. It then verifies the real
`https://smartploy.obumai.com` boundary:

- DNS resolves;
- HTTPS/TLS verification succeeds normally;
- Cloudflare edge evidence is present;
- unauthenticated root is protected rather than returning public HTTP 200;
- unauthenticated `/api/v1/dashboard` is protected rather than returning HTTP 200;
- 5xx responses fail the gate;
- 3xx protection is accepted only when the redirect targets a `*.cloudflareaccess.com`
  `/cdn-cgi/access/` endpoint.

The public probe does **not** follow redirects and captures only status, `cf-ray`, `server`, and
`location`. It never prints cookies, JWTs, Access assertions, authorization headers, database
credentials or source credentials.

Expected successful output is intentionally compact:

~~~text
origin_health=pass
dns=pass
tls=pass
cloudflare_edge=pass
access_root=protected
access_api=protected
live_acceptance=pass
~~~

This gate should be run after every change to the public SmartPloy route, Cloudflare Access application,
or production ingress.


## Release evidence bundle

After a successful deployment, create a durable non-secret release record:

~~~bash
bash deploy/personal/scripts/release-evidence.sh
~~~

The command takes the production-operation lock so it cannot race a deploy/restore, but it does not
mutate application/database/runtime state. It requires the repository HEAD to match the recorded
`deployed-sha`, then reruns the no-mutation preflight, live key-only environment-boundary smoke, local
health contract, and latest backup checksum/metadata validation.

It writes a private evidence file and SHA256 sidecar under `SMARTPLOY_DEPLOY_STATE_DIR`. The manifest
contains exact deployed/code SHA binding, policy/Compose hashes, non-secret readiness booleans, worker
task count, backup basename/checksum validity, and gate results. It does not contain database URLs or
passwords, Access issuer/audience/email, JWT/cookies, ObumAI headers, source credentials, job content,
CV content, or application content.

To include the public DNS/TLS/Cloudflare Access acceptance result after the public route exists:

~~~bash
bash deploy/personal/scripts/release-evidence.sh --online
~~~

The online mode reuses `live-acceptance.sh` and records only its compact pass/protected status fields.

A SHA mismatch between the checked-out code and `deployed-sha` fails closed. This prevents an evidence
bundle from certifying a different working tree than the one recorded as deployed.
