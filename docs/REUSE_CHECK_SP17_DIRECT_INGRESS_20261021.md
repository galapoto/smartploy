# SP17 — SmartPloy OIDC direct HTTPS cutover: mandatory run evidence

Date: 21 October 2026  
Stage: Production launch gate / AutoApply user access  
Baseline main SHA: `7178e31afaef5ec31d51e91b59daebf7f59f67be`  
Production receipt: operator-supplied OVH output on 21 October.

## Observed failure / what changed versus prior stage

The operator's full deployment reached new images, successful migrations,
healthy postgres/API/worker/web and local Ollama. The final
`live-acceptance.sh` check rejected the publicly probed production root
with `production response lacks Cloudflare edge evidence`. Consequently
`deployed-sha` was **not** advanced, even though the new containers ran.
The earlier app-level checks were prevented from running, and a real
ZITADEL login has **not** been verified.

## Proof of reuse before authoring

1. **Reused** the original `smartploy/live_acceptance.py` (baseline blob
   `57f501c26b6506c8b8b9eaef151535d79827593b`). It already provides
   exact production origin-health validation, signed-out private API
   checks, and strict issuer redirect checks; none were replaced.
2. **Reused/adapted** the actual OVH live gate
   `deploy/personal/scripts/live-acceptance.sh` (baseline blob
   `7e3edb9c9660da388355ba5a15163d7258c366a8`). It already validates
   DNS and HTTPS using curl's default certificate verification and checks
   private route access before writing the release receipt.
3. **Reused/expanded** `tests/test_live_acceptance.py` (baseline blob
   `dc1d8b4dcdd49a11fb495e47fe75e589ac2be7bd`) instead of building a
   second acceptance harness.
4. **Reused** the pre-existing immutable production OIDC profile, Caddy
   reverse proxy, ZITADEL client, backup/migrations, Docker image checks,
   and direct ATS / consented draft infrastructure. None were forked.

## Production code adapted in place

- OIDC acceptance no longer requires `cf-ray` or `server: cloudflare`
  for `https://smartploy.komplyint.fi`. This hostname's documented
  public DNS routes directly to OVH Caddy; the public HTTPS hostname,
  certificate, API isolation and trusted OIDC issuer remain mandatory.
- Legacy Cloudflare Access protection retains its original edge check.
- Original shell now emits limited diagnostic fields for the public
  root, signed-out dashboard and login initiation: **numeric HTTP
  statuses and ingress classification only**. It does not print OAuth
  state, redirect URLs, credentials, cookies or private environment.
- Extra tests cover a direct TLS ingress and reject a Cloudflare
  Access challenge, public account API, upstream 502 and evil redirect.

## Newly authored from scratch

- This run ledger / reuse audit and additional regression test cases.
- **No** new auth stack, ATS connector, database schema, daemon, CI
  platform, new network endpoint or final-submit mechanism.

## What is NOT proven by the source change

- Real public root `200`, signed-out dashboard `401` and login
  redirect to `auth.komplyint.fi` require rerunning the gate on OVH.
- Interactive two-account login/ownership isolation and verified
  private AutoApply draft require an actual user acceptance session.
- Automatic **employer** submissions are not authorized by this fix.
  The existing reviewed partner gate and provider ACK are mandatory.

## Progress rubric

| Check | Baseline | After this source run |
|---|---|---|
| GitHub release tree | `7178e31` | Incremental SP17 branch change |
| New release images on OVH | Healthy (operator log) | No additional deployment yet |
| Public OIDC shell gate | Rejected absent Cloudflare header | Header-agnostic for OIDC; status still strict |
| Private API / trusted issuer | Not reached during failed rollout | Same existing protected contracts |
| End-to-end user AutoApply | Not accepted | Pending live sign-in and owned draft |
| Employer submit | Not authorized | Unchanged; partner-only with explicit rights |

Do not label a changed source file as an installed production fix until
CI for the exact SHA and the new OVH acceptance both pass.
