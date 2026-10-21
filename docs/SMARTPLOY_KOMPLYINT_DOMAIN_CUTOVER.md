# SmartPloy → smartploy.komplyint.fi production cutover

Updated 21 October 2026. **AutoApply is the first delivery priority.**
This is a safe, opt-in rollout plan, **not proof of a public deployment**.

## Already implemented / reused

- Original `smartploy/oidc.py` OIDC client, server-side sessions, same-origin
  CSRF/Host protection and ZITADEL compatibility remain unchanged.
- The existing immutable `deploy/personal/runtime.oidc.production.env`
  now selects `https://smartploy.komplyint.fi` as the *only* allowed
  first-party HTTPS origin. The Cloudflare Access **legacy**
  `runtime.production.env` continues to select `smartploy.obumai.com`
  until explicitly retired; no wildcard/multi-tenant credential acceptance.
- Original `validate-runtime-policy.sh` now enforces a different
  allowlisted exact origin for each of the two existing identity profiles.
  Original `preflight.sh` derives OIDC callback/logout from that
  verified immutable policy: `https://smartploy.komplyint.fi/auth/callback`
  and `https://smartploy.komplyint.fi/auth/logged-out`.
- Existing `web.Caddyfile` now forwards the incoming exact Host to
  the API instead of rewriting it to the old domain. `TrustedHostMiddleware`
  still rejects incorrect hosts; no CORS wildcard or login bypass.
- The live discovery document at `https://auth.komplyint.fi/.well-known/openid-configuration`
  advertises issuer `https://auth.komplyint.fi`, public-client
  `none` token authentication and PKCE S256. Update the private
  OVH issuer setting; the previous `auth.obumai.com` example was wrong
  for this identity instance.
- The pre-deploy online check now probes the canonical hostname from
  the immutable selected policy, not the legacy ObumAI hostname.
  It verifies DNS, HTTPS and matching issuer PKCE metadata but cannot
  require the new SPA to be live **before deployment**. The strict
  post-deploy acceptance remains the gate for actual public login.
- Original read-only live acceptance derives DNS, public HTTPS and
  origin-health host from the selected policy, then requires a public
  SPA shell, unauthenticated private API 401 and a redirect to the
  configured trusted OIDC issuer, **not** Cloudflare Access sign-in.
- `Caddyfile.host.example` provides ONLY the new hostname reverse-proxy
  block; it makes no changes to the existing production hostname.
  `Caddyfile.legacy-redirect.example` is a separate **optional**
  redirect and must NOT be installed until the real new-domain login,
  private API, AutoApply and TLS acceptance have passed.
  Neither example is automatically installed.

## Required operational cutover, in order

1. **AutoApply code:** keep the existing five reviewed Finland ATS feeds,
   source-priority worker fix, revocable opt-in, approved career evidence
   and strict final-employer-submit rights. Promote only an audited,
   native ObumDelivery-approved, exact-source build.
2. **DNS — VERIFIED 21 October 2026:** public authoritative
   Euronic/Domainkeskus DNS now resolves `smartploy.komplyint.fi`
   directly to **51.75.61.214**, TTL **600 seconds**. The owner
   confirmed that this is the intended OVH server. The public HTTPS
   root and `/healthz` remain unreachable, so server ingress/TLS
   and production application activation are still outstanding.
   Do not change any existing `auth`, `proctor` or apex records.
3. **TLS/edge:** after identifying the OVH ingress actually serving
   `auth.komplyint.fi`, ADD ONLY the new `Caddyfile.host.example`
   site block if the existing proxy is Caddy, or its equivalent for
   the installed proxy, without replacing or restarting other services
   without an approved change window. The old-host redirect is NOT
   included in this file.
   verify certificate, HTTPS, a public static shell, private API
   unauthenticated 401. With the currently documented direct DNS A
   record to OVH, verify the existing Caddy HTTPS/TLS ingress: no
   `cf-ray` or `server: cloudflare` header is expected or required.
   If traffic is subsequently routed through the Cloudflare proxy,
   configure its **Access bypass for this application hostname** and
   preserve HTTPS/WAF as applicable. In either topology the actual
   authentication is first-party ZITADEL. Cloudflare Access must never
   intercept `/auth/login` or `/auth/callback`.
4. **Identity:** register **exactly** the new login callback
   `https://smartploy.komplyint.fi/auth/callback` and signed-out
   redirect `https://smartploy.komplyint.fi/auth/logged-out` for the
   existing approved ZITADEL OIDC public client. Keep issuer secrets,
   API tokens and session cookies in server-only configuration. Do
   not infer successful identity migration from a redirect alone.
5. **Private config:** change the already-private `deploy/personal/env`
   callback and logout variables to the exact values above without
   clobbering other secrets; validate required origin-specific OIDC
   app settings and confirm the operator selected `oidc`.
6. **Release gate:** require CI for exact SHA, native ObumDelivery
   evidence including rejection of a negative control, full backup,
   healthy PostgreSQL migration, read-only live-acceptance result,
   a genuine two-user sign-in/switch/CSRF session test, at least one
   fresh actual ATS poll, one real account's private auto-draft save,
   and no unapproved employer POST. Real submissions additionally
   require employer-side rights, a real reviewed applicant gesture,
   an exact partner job and a stored provider `applicationId`.
7. **Redirect:** once the new host is independently verified,
   separately enable the optional *temporary* old-domain redirect
   from `Caddyfile.legacy-redirect.example` if that legacy
   hostname is actually routed through the same ingress. When rollback
   is needed, revert this redirect, restore the old exact Cloudflare
   identity policy and verified old Caddy origin before accepting traffic.
   Do **not** share cookies between unrelated registered domains.

## Exact release blockers visible from repository inspection

- No direct verification of DNS, valid TLS, Cloudflare Access bypass,
  real ZITADEL login/registration, new OVH running SHA or native CI
  from this connected GitHub-only source workflow.
- Employer-specific Lever partner keys and authorization must be
  obtained from the actual employers. Job posting visibility and
  opt-in draft preparation **do not authorize** a final application.
- No source file or deployment job in this PR directly changes live
  Domainkeskus DNS or OVH Caddy; operator-controlled rollout remains
  necessary. The system must not claim the domain has moved until
  the new URL is publicly reachable and first-party sessions pass.

## SP15s — DNS-complete / OVH-host cutover verification

The user confirmed the Domainkeskus A record and independent public
DNS returned `51.75.61.214`, TTL `600`. External HTTPS fetches of
`/` and `/healthz` remain unreachable as of this verification.

The original release pipeline had a SECOND hostname bug: although
the new OIDC preflight chose the correct domain, `deploy.sh`,
`restore.sh`, `assert-healthy-stack.sh`, `assert-running-images.sh`,
`release-evidence.sh` and `diagnose-origin-502.sh` still checked
`smartploy.obumai.com` or hard-coded its Cloudflare policy.
They now reuse the **exact selected, verified immutable runtime
identity policy**. New tests execute the original embedded Python
production health validation with both policy origins and negative
cross-origin cases. No hostname wildcard or shared domain cookies.
The OIDC pre-deploy TLS check can tolerate a 502 from an installed
new-host reverse proxy *before first deployment*, but the original
post-deploy live-acceptance rejects any 5xx and must pass the
ZITADEL redirect + private API before recording a deployed SHA.

The sample Caddy new-host site and optional legacy redirect are now
separate files, so a well-intended initial install cannot silently
redirect users away from the existing hostname. These code changes
are NOT proof that the OVH proxy was installed or that the app runs.

## SP17 — 21 October deployment gate correction (source only)

The operator's next OVH run successfully fetched and checked out the integrated
`7178e31` release, passed private OIDC preflight, built both images, backed up
PostgreSQL, applied migrations, connected local Ollama and brought the Postgres,
API, worker and web services healthy. **The post-deploy gate failed** before
recording `deployed-sha`, with `production response lacks Cloudflare edge
evidence`. The running containers and the deployment receipt are therefore
not the same thing. Do not claim public login or AutoApply acceptance.

The previous `smartploy/live_acceptance.py` OIDC validator incorrectly demanded
Cloudflare response headers even though the operator's approved production DNS
points directly to an OVH Caddy HTTPS ingress. SP17 reuses that exact TLS probe
and the original origin-health, 401 private API and trusted issuer redirect
gates, but no longer treats an optional reverse-proxy brand header as user
authentication. Cloudflare **Access** challenges, private API `200`, unrelated
login redirects, invalid issuer and non-`200` public root still fail closed.
Legacy Cloudflare Access acceptance is unchanged.

The original shell now reports only the public root/API/login numeric HTTP
statuses and ingress classification to assist nonsecret follow-up diagnostics.
Release success still requires a fresh SHA-matched CI run, the OVH read-only
public OIDC acceptance, a real ZITADEL account login and an account-owned draft.
Employer submissions remain separately authorization gated.
