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
- Original read-only live acceptance derives DNS, public HTTPS and
  origin-health host from the selected policy, then requires a public
  SPA shell, unauthenticated private API 401 and a redirect to the
  configured trusted OIDC issuer, **not** Cloudflare Access sign-in.
- `Caddyfile.host.example` provides a staged reverse-proxy route
  for the new hostname and a *temporary* legacy redirect. Its contents
  are **not** installed automatically.

## Required operational cutover, in order

1. **AutoApply code:** keep the existing five reviewed Finland ATS feeds,
   source-priority worker fix, revocable opt-in, approved career evidence
   and strict final-employer-submit rights. Promote only an audited,
   native ObumDelivery-approved, exact-source build.
2. **DNS:** set the new `smartploy` host in the `komplyint.fi` DNS zone
   to the approved OVH/Cloudflare ingress destination already used
   by the organization. Do not guess an IP, CNAME target or tunnel ID.
   Confirm public DNS resolution and the absence of a conflicting record.
3. **TLS/edge:** install `Caddyfile.host.example` or its equivalent
   on the approved OVH ingress **after** DNS control is confirmed;
   verify certificate, HTTPS, a public static shell, private API
   unauthenticated 401. Configure Cloudflare edge/WAF so
   `smartploy.komplyint.fi` **bypasses Cloudflare Access login** but
   keeps TLS/WAF, and retain first-party OIDC authentication. Cloudflare
   Access must not intercept `/auth/login` or `/auth/callback`.
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
   enable the optional *temporary* old-domain redirect. When rollback
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
