# SP18 — First-party OIDC callback browser-binding incident (2026-10-22)

## Project-plan scope
Core capability: usable first-party ZITADEL sign-in to the personal SmartPloy job-search and application-draft workspace. No job source, employer submission, production database or user permissions are modified by this product-source fix.

## Evidence from the reported incident
- The public Komplyint origin resolved to OVH, TLS verified, `/` and `/healthz` returned HTTP 200; unauthenticated `/api/v1/dashboard` returned 401; `/auth/login` returned 302.
- The actual incognito browser reached `/auth/callback?code=…` after ZITADEL and received `401 OIDC callback validation failed`.
- Authlib v1.8 requires a browser-specific marker in `request.session` to accompany cached OAuth state. Previous SmartPloy issued this marker with `request.scope.setdefault("session", {})` inside `/auth/login`, but the dictionary was never persisted to the callback.
- The old test used `FakeOIDCClient.authorize_access_token`, which does not check Authlib's real marker, so it missed the failure. The cache-only test checked PKCE/nonce but never completed a callback.

## Reuse-first evidence
| Source already implemented | Action | Why |
| --- | --- | --- |
| `smartploy/oidc.py` Authlib OAuth2/OpenID client | Reused, unchanged state/PKCE/nonce validation | Uses vetted OAuth implementation rather than writing a token verifier |
| Existing PostgreSQL `smartploy_oidc_state` cache | Reused | Durable private multi-request state; no extra store/service |
| Existing `__Host-smartploy_session` authenticated app cookie | Reused, unchanged | Separate from short-lived login flow cookie |
| `smartploy/api.py` ZITADEL login/callback routes | Adapted in place | Minimal change to existing public-client integration |
| Production OIDC allowlist and exact callback URL | Reused, unchanged | No new credentials, client registration or auth bypass |

## Newly implemented from scratch
- `__Host-smartploy_oidc_flow`: a short-lived (state TTL), Secure, HttpOnly, SameSite=Lax, host-only random browser cookie; independent from the permanent app session.
- An opaque one-time **hashed cookie-to-state binding** in the existing cache. A callback must present the correct browser cookie before any token request. Invalid or missing cookies cannot consume a legitimate flow.
- On successful independent browser binding, restore the short-lived **Authlib marker** in `request.scope["session"]`, allowing Authlib to keep enforcing its own state/PKCE/nonce validation. The binding is deleted before code exchange; success clears the flow cookie.
- Real Authlib `authorize_redirect` / `authorize_access_token` regression test with an isolated fake token response; no ZITADEL or employer traffic.

## Threat model and regression gates
- Cross-browser code/state injection is blocked, not just a state equality string check.
- The browser cookie contains no OAuth code, nonce, PKCE verifier, ID token, applicant profile or CV.
- Callback replays cannot mint a second session; a subsequent login replaces the previous in-browser binding.
- `SMARTPLOY_OIDC_STATE_TTL_SECONDS` bounds the flow cache and cookie; no new production secret is required.
- The 401 error remains generic; do not log or disclose authorization code or state.
- Preserve protected API 401 and authenticated app/session behavior; no Cloudflare Access reintroduction.

## Changes from previous stage
Before SP18: SP17 public TLS/root/issuer checks and healthy Docker stack; real first-party sign-in failed after ZITADEL.
After SP18 source candidate: the browser-callback binding is now expressible and tested end-to-end with real Authlib session expectations; **actual production browser success is not claimed until a new SHA is deployed and tested**.

## Evidence and release status
- Repository: `galapoto/smartploy`
- Base: `2ba4415760bad6c1d2f694238e5d4da037af93c4`
- Candidate branch: `fix/sp18-browser-bound-oidc-callback-20261022`
- Required CI: pytest/PostgreSQL, real-callback negative tests, frontend, browser, Docker stack, source receipt.
- OVH deployment: NOT executed by this source change.
- Real ZITADEL user acceptance: NOT executed.
- Woodpecker native activation: still blocked on separately observed HTTP 403; GitHub Actions is the available product CI.

## Next actions
Wait for full candidate CI, merge only verified head, run the guarded existing OVH release for the immutable merged-main SHA, open a new private browser and go to `https://smartploy.komplyint.fi/auth/login` (never refresh an old code URL). Confirm a 303 to /, session cookie, and authenticated /api/v1/session. Continue separate Woodpecker admission triage without production CI grants.
