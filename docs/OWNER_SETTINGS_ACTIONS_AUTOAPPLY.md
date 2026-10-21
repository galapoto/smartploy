# SmartPloy — owner settings needed for first real AutoApply release

Reviewed 21 October 2026. Product priority: **fetch suitable Finnish IT jobs,
prepare truthful private drafts automatically, and show evidence of any
applications actually sent**. This file is an operational handoff, not proof
of production settings or employer applications. It contains no secrets.

## Settings that the project owner can complete now

### 1. ZITADEL first-party SmartPloy login (owner action)

Within the authoritative ZITADEL project (or its delegated administrator),
create/update the OIDC application used by SmartPloy. Reuse the existing
project and identity instance; **do not create another auth server**.
The original `smartploy/oidc.py` uses Authorization Code + PKCE S256
with a **public client** (`token_endpoint_auth_method=none`, no
frontend client secret). Production OIDC profile strictly requires:

| Field | Value |
| --- | --- |
| Application display name | SmartPloy |
| Application type | OIDC web app / public client, Authorization Code with PKCE S256 |
| Redirect URI | `https://smartploy.komplyint.fi/auth/callback` |
| Post-logout redirect URI | `https://smartploy.komplyint.fi/auth/logged-out` |
| Redirect scheme | HTTPS only; production/dev mode OFF |
| Requested scopes | `openid profile email` |
| Issuer URL | The **actual** organization's ZITADEL origin (copy from its discovery configuration, not from a guess) |
| Client ID | Copy the application's public Client ID into the **private OVH env**, not the repo |

A valid ZITADEL issuer's `/.well-known/openid-configuration`
must be reachable from SmartPloy's API container.
Do not send an administrator PAT, client secret, user password or
provider cookie in chat.

Official reference: https://zitadel.com/docs/guides/manage/console/applications-overview

### 2. Domain DNS and Cloudflare Access policy (owner action)

Determine which provider is **authoritative for komplyint.fi DNS**.
If Domainkeskus provides DNS for the domain, edit that DNS zone; if
Cloudflare nameservers are authoritative, edit Cloudflare DNS instead.
Add the exact `smartploy.komplyint.fi` host to the **already approved
OVH/Cloudflare ingress target** used for the SmartPloy deployment.

Never invent the origin IP, reuse someone else's tunnel, or replace
`proctor.komplyint.fi` DNS/Access rules. The operator must choose
the correct A/AAAA or CNAME record based on the deployed ingress.
Check public DNS and working TLS **before** redirecting the old domain.

- Keep HTTPS/TLS and firewall/WAF protection.
- If the route passes Cloudflare Zero Trust Access, exclude
  `smartploy.komplyint.fi` from Access challenges. Do **not**
  redirect users to `*.cloudflareaccess.com` for normal SmartPloy login.
- Let the application enforce its own ZITADEL OIDC + server session.
  `/auth/login`, `/auth/callback` and `/api/*` must reach SmartPloy.
- Leave `smartploy.obumai.com` in place until real TLS/OIDC acceptance
  works at the new URL. Only then consider a temporary redirect.

### 3. OVH-only release settings (operator deployment action)

Use the original private `/srv/obum/stacks/smartploy/deploy/personal/env`
file, never commit it. Its relevant keys for this target are:

```text
SMARTPLOY_OIDC_ISSUER=<verified existing ZITADEL issuer HTTPS origin>
SMARTPLOY_OIDC_CLIENT_ID=<registered public client ID>
SMARTPLOY_OIDC_REDIRECT_URI=https://smartploy.komplyint.fi/auth/callback
SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI=https://smartploy.komplyint.fi/auth/logged-out
SMARTPLOY_OIDC_SCOPE=openid profile email
SMARTPLOY_WORKER_AUTO_DRAFT_ENABLED=true
SMARTPLOY_WORKER_AUTO_DRAFT_CADENCE_SECONDS=120
SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED=false
SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=<operator-reviewed five-source JSON or approved equivalent>
SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=
```

`SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc` is the **host-side
operator command environment selector**, not an editable deployment env
entry. The immutable checked-in
`deploy/personal/runtime.oidc.production.env` supplies the
canonical `https://smartploy.komplyint.fi` origin, exact allowed host,
and disabled Cloudflare Access assertions. The original
`validate-runtime-policy.sh`, `preflight.sh` and
`live-acceptance.sh` must pass before the deployment SHA is recorded.

**Proof required before saying live:** native ObumDelivery
GREEN exact SHA and intentional RED negative control, owner-approved
source SHA, versioned database backup/migrations, healthy API/web/worker,
real DNS/TLS/ZITADEL two-account and CSRF tests, and at least one
fresh public source job -> genuine applicant-approved private draft.

### 4. Real employer submission (later, employer-specific)

The already-built official Lever partner API submission path is
restricted to employers who have explicitly authorized the integration,
approved the precise job/form and issued the appropriate credential.
**Seeing a public vacancy does not grant applicant API permission.**
If no employer partner credential is available, first ship reliable
source discovery, owner-verified documents, and supervised final
application handoff; never invent a provider application ID or mark
a draft as submitted. Candidate review/consent and employer terms apply.

## What is not needed from the user

- No local shell work to run GitHub regression tests or configure
  SmartPloy's source code; those are implementation tasks.
- No employer secret to browse public vacancies or to generate
  private draft applications.
- No password or access token in chat. Save credentials through
  the original private OVH/ZITADEL administrator settings.

## Release-state checklist (facts, not forecast)

- [x] First-party OIDC canonical URLs committed in source
- [x] Reviewed public ATS adapters and opt-in private draft worker built
- [x] Evidence-change recheck added before guarded draft save
- [ ] User/operator verified new DNS record and HTTPS certificate
- [ ] User/operator registered ZITADEL OIDC callback + post-logout URLs
- [ ] New hostname no longer presents Cloudflare Access login
- [ ] Native ObumDelivery exact SHA + deliberate RED evidence
- [ ] OVH exact-SHA deployment + live read-only health / ATS / draft checks
- [ ] Approved employer partner credentials + real provider ACK for actual submissions

Only check a box when supported by a real operational receipt.
