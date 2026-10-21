# SmartPloy — AutoApply and Komplyint release readiness

Checkpoint: 21 October 2026. Priority order: **AutoApply actually usable**
→ safe first-party ZITADEL sign-in at `smartploy.komplyint.fi` →
source-health and private application review acceptance → authorized
employer handoff. This document distinguishes operator-observed live
facts from tested GitHub source and unreleased functionality.

## Production facts confirmed by the operator

- OVH machine `obum-core-01` continues to run Git SHA
  `fc94e78e779650e781277ee1056ec92cd26a6e98`.
- The owner created the ZITADEL public OIDC application and supplied
  its exact callbacks for `smartploy.komplyint.fi`; issuer
  `https://auth.komplyint.fi`. Its public Client ID and callbacks
  were placed in **private** `deploy/personal/env`, not Git.
- The owner added and externally confirmed the DNS A record for
  `smartploy.komplyint.fi` on the existing approved OVH ingress.
- The owner installed a **separate Caddy hostname** forwarding to
  the existing loopback `127.0.0.1:8091`. Caddy syntax validated;
  the browser reached the old SmartPloy Cloudflare-auth error page.
- The owner completed the original-release PostgreSQL secret rotation:
  `rotation=PASS`, `database_backup=verified`,
  `old_password_revoked=true`,
  `private_config_updated=true`,
  `postgres_api_worker_recreated=true`,
  `live_gateway_health=verified`,
  `exact_running_release_sha=fc94e78e779650e781277ee1056ec92cd26a6e98`,
  `identity_mode=unchanged_cloudflare`,
  `autoapply_upgrade=not_yet_deployed`.
  These are **operator-reported** receipts, not remotely read from OVH.
  Previous private env backups may contain obsolete credentials and
  should remain root-only or eventually be purged under a retention
  policy. Never paste or commit the old or new password.

## Built and reused, but not yet live

The integrated release train is [PR #173](https://github.com/galapoto/smartploy/pull/173).
It reuses, without duplicating, the already-built PostgreSQL job store,
direct ATS adapters, resume fact approval, per-user search preferences,
private application workspaces, durable task scheduler, browser receipt
gate, ZITADEL OIDC client, Caddy reverse proxy and existing deployment
backup / restore scripts.

**Core AutoApply:** consented personal IT matches → trusted, fresh
official-source validation → approved evidence and current CV rechecked
at guarded save → idempotent private applications. The first worker
cycle ingests due official sources before matching; manual opt-in,
role changes and approved profile evidence trigger private drafting
without waiting for background cadence. Background local draft cadence
is two minutes; ATS sources retain their own rate limits. Revocation,
multiple accounts, stale feeds and unapproved CV data fail closed.
Neither an auto-generated draft nor a browser packet equals a sent
employer application.

**New 21 Oct OIDC release fix:** the original Compose API and web
`healthcheck` entries hard-coded the old
`smartploy.obumai.com` Host, which would permanently mark the new
OIDC containers unhealthy under
`SMARTPLOY_ALLOWED_HOSTS=smartploy.komplyint.fi`. Both probes now reuse
the original **immutable selected production identity policy**:
API checks use their own exact allowed-Host env, and web health
gets the exact selected hostname from Compose interpolation.
A full synthetic Docker Compose production-stack test first runs
legacy Cloudflare and then restarts only the same application images
in the new OIDC profile, requiring healthy Postgres/API/worker/web,
OIDC `public_origin`, legacy Host rejection, and a signed-out API
401. This is **not** real ZITADEL interactive login acceptance.

**Native ObumDelivery gate:** the already-existing
`scripts/obumdelivery_ci_gate.py` qualifies a checked-out SHA and
creates a per-source synthetic-test HOLD receipt. The Woodpecker
pipeline now exercises its deliberate rejection path
(`CI_NEGATIVE_PROBE=1` must return **41** and
`EXPECTED_RED_NEGATIVE_PROBE`) before running real tests.
The pipeline continues to say `PRODUCTION_RELEASE_GATE_HOLD` and
does not deploy, grant partner rights, or send employer applications.
A GitHub Actions green result is **not** native Woodpecker proof.

## Release transition steps, in the required order

1. Verify the **exact source SHA** has completed GitHub and native
   ObumDelivery tests (including the native expected-RED probe).
   Review the 160+ commits / 170+ changed files of integration
   PR #173. Reconcile competing draft pipelines #169 / #171 / #172,
   avoid migration-number collisions, and complete independent
   review of first-party auth, account isolation and employer APIs.
2. Once approved, merge exactly the reviewed tree to `main`
   without creating a different untested release. Record the
   new main SHA and keep the previous known-good SHA.
3. On OVH, run the existing **read-only** OIDC production preflight
   for that *checked-out* code with host selection
   `SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc`. Reuse the existing
   private env; do not paste it, copy a GitHub sample over it,
   change DNS/Caddy again, or enable global AI forwarding.
   DNS/TLS, exact callback, issuer PKCE S256 and Compose env
   boundaries must pass. No password rotation is required again.
4. Run the original `deploy/personal/scripts/deploy.sh` with both
   `SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc` and
   `SMARTPLOY_RELEASE_APPROVED_SHA=<exact-reviewed-main-sha>`.
   The existing deploy script holds the operation lease, builds
   the exact source, backs up PostgreSQL, migrates the database,
   brings the API/worker/web up, checks the selected Host,
   verifies image identity and runs **read-only public OIDC
   live-acceptance** before writing `deployed-sha`.
   This is an explicit approved production action, not performed
   through this GitHub source workflow.
5. Complete a real, operator-observed two-account ZITADEL login,
   CSRF/session isolation, approved CV/profile, per-user AutoApply
   enable/change/revocation, at least one fresh official ATS poll,
   and a saved private application for a real owned profile.
   Use existing `scripts/check_ats_readiness.py` and
   `scripts/check_application_runtime.py` for nonsecret status
   reports. The live worker must actually run with the browser
   closed. Do not claim an application has been sent without an
   employer-signed/provider-issued acknowledgment.
6. Only enable employer final submit for individually approved
   partner postings/forms with a real applicant final review,
   provider permissions, idempotency and durable returned
   application receipt. Otherwise leave external actions disabled.

## Current delivery labels

| Workstream | State | What constitutes completion |
| --- | --- | --- |
| Database incident containment | **Done — operator receipt** | Old credential revoked; healthy old release |
| DNS and Caddy edge | **Done — operator receipt** | New Host resolves and reaches old app |
| ZITADEL app + private env | **Configured** | Needs live two-account login |
| Core automatic matching and private drafts | **Source complete / production pending** | Same account opt-in creates actual reviewable draft from live jobs |
| Dual-profile Docker health and public API | **CI-verified** | Needs exact-sha OVH live acceptance |
| Native ObumDelivery | **Blocked (receipt unavailable)** | Exact checkout green, expected RED, explicit review |
| Merge to `main` | **Blocked (release gate)** | Reviewed migration/integration |
| Final employer submission | **Not complete** | Approved employer rights + real provider ACK |

No elapsed-time estimates are claimed for items requiring live credentials,
native CI admission or employer authorization.
