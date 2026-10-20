# SP15i — safe OIDC and authorized-partner activation on OVH (20 Oct 2026)

**This is release-path source engineering.** It does not claim that OVH,
Cloudflare, ZITADEL or Lever credentials were changed, that a real applicant
signed in, or that any employer application was submitted.

## Before writing: verified actual reusable components

- Existing first-party OIDC (ZITADEL-compatible) implementation in
  `smartploy/oidc.py` original blob
  `015ca5df354979b090384b5aa6efc2a3f34e2cb6`:
  Authlib Authorization Code+PKCE/nonce, opaque host-only HttpOnly SameSite
  session, PostgreSQL session and state stores, exact-origin CSRF and
  verified stable account binding. **Direct reuse, no new authentication**.
- Existing Cloudflare Access production profile
  `deploy/personal/runtime.production.env` blob
  `5beaa48522dfa8056cf461f969325083c25fb7fc`
  and `validate-runtime-policy.sh` original
  `89b22839ff7d34d5af042d28abb1fae85eb91c34`.
  Legacy policy remains DEFAULT and an exact approved fallback.
- Existing Docker Compose API/worker/web/Postgres service segregation
  `deploy/personal/docker-compose.yml` blob
  `79b5405b0871ae6348f1ff55335fcb8fb04e8272`,
  backup/restore/deploy scripts, original
  `preflight.sh` blob `19d1a078ebc8366c310cb4016b3227fa1554b23e`,
  original public TLS/edge/origin validator
  `smartploy/live_acceptance.py` blob
  `149f179d6dd0fd933c3552ac8a92b7f72303c493` (script) and
  Python helper in existing first-party tree.
- Existing SP15f Lever direct employer API
  `smartploy/lever_partner_submit.py`: exact org/posting and employer
  admin-issued key, approved standard-form terms, independently reviewed
  rights, reviewed candidate CV/contact and original sticky claim. **Not
  rebuilt**. It expected environment variables that the actual production
  Compose API did not yet receive. This was an actual release blocker.
- Existing ObumDelivery isolated source CI pipeline
  `.woodpecker/smartploy.yaml` (blob
  `e5affff6e473730990fb0f289f96d859635ddb39`) and original
  exact-checkout receipt, no paid CI or new CI platform.

## Minimal new or adapted code

1. **NEW** `runtime.oidc.production.env`: explicit immutable first-party
   authentication, Cloudflare *edge remains for TLS/WAF/reverse proxy* but
   Cloudflare **Access identity assertions are disabled**.
   **NEW** `select-runtime-policy.sh` accepts only `cloudflare` or
   `oidc`; never a caller-chosen arbitrary file. Original Cloudflare
   profile remains default. Adapted original `validate-runtime-policy.sh`
   validates EXACT content of either selected profile, rejecting
   unaudited extra variables.
2. **ADAPTED IN PLACE** original
   `preflight.sh`, `deploy.sh`, `backup.sh`, `restore.sh`,
   `release-evidence.sh` and `smoke-env-boundaries.sh` to share
   that one source of selected identity policy. OIDC mode demands
   HTTPS-only issuer, real registered client ID, exact callback/logout
   URLs, a private 0600 env file and original loopback-only networking;
   missing/inconsistent configuration fails closed. An OIDC rollout
   requires exact operator-approved code SHA and public web root
   reachability before switching services. Deployment and restore
   record/check the selected identity profile to prevent accidental
   rollback with a different identity policy.
3. **ADAPTED IN PLACE** original production Compose. Access issuer/
   audience/email are optional only when Access is disabled by the
   selected immutable OIDC policy. Three API-only partner credential
   slots + an exact per-posting reviewed-configuration JSON variable
   are passed to **API ONLY**. No partner keys in frontend/worker/
   postgres. No new network port, secret-storage service, new AI
   engine or browser. The original partner repository still blocks
   missing/unreviewed jobs. The original preflight verifies at most
   100 exact configured postings, independently reviewed standard form,
   API-only key slot, secret format and no unused credential.
4. **REUSED** original minimal public health/readiness schema rather
   than exposing login internals there. The deploy-time immutable OIDC
   profile is verified out of band, origin storage must be ready with
   Access JWT disabled, the public static login shell must return 200
   over Cloudflare TLS edge, private `/api/v1/dashboard` must return
   signed-out 401, and `/auth/login` must redirect to the EXACT
   configured trusted HTTPS ZITADEL issuer. A Cloudflare Access challenge, unrelated redirect,
   public API 200, missing session backend or invalid origin is a
   RED release block. The original Cloudflare Access release probes
   remain unchanged for legacy profile.
5. **NEW** isolated source regression tests exercising exact immutable
   policy selection, allowed/denied modes, untampered source, partner
   secret boundaries, and OIDC login/root/API/health positive and
   negative scenarios. Reuses existing Python/pytest/live-acceptance
   tests and no actual employer or login network traffic.

## Required production acceptance; NOT executed by this PR

The production operator must register an actual OIDC public client in
the already selected ZITADEL issuer with precisely
`https://smartploy.obumai.com/auth/callback`, and set registered
issuer/client credentials in the private server env. They must
configure Cloudflare routing to allow the SmartPloy public static
login shell and `/auth/*` through Cloudflare's TLS edge **without
requiring Cloudflare Access login**, while keeping the origin
loopback-only and application cookie auth strict.

Only after a native ObumDelivery exact-SHA PASS plus deliberate
negative RED and owner-approved backup and rollback, an operator
may select the OIDC release profile and provide the exact approved
revision. The existing deploy script must pass preflight, migrate
the existing PostgreSQL storage, verify images/health and create a
release receipt. The production operator must then verify in a
real, consented signed-in browser: identity, tenant CV isolation,
same-origin CSRF, logout/relogin, approved employer document and
the correct protected API denial when signed out.

For actual partner applications, obtain a genuine employer
Super Admin-issued Lever API key with written authorization for the
posting, two independently authorized reviewers, exact standard-form
and consent evidence. With that configured in only the API container,
a permitted applicant can review, explicitly confirm, submit once and
see the official `applicationId` and `provider_acknowledged` saved
status after reload. No employer key, permission, candidate final
approval or posting means **zero direct POSTs**.

Other ATS still use manual final submit/approved browser companion
until their legitimate rights and reliable per-site adapter exist.
This change does not enable Chrome companion final auto click or
unattended applications. A green source CI run is not live acceptance.

**Hold** actual production changes until live provider, edge, native CI,
ZITADEL and owner approval are independently evidenced. In particular,
selecting OIDC in code does NOT disable Cloudflare Access at the edge.
