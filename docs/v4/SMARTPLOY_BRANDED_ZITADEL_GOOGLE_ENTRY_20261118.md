# SmartPloy branded ZITADEL and Google entry
Date: 18 November 2026. Authority: SmartPloy V4 production-first contract, section 1.1, 4-7 and 12, and 2027 V3 UI and reuse applicability. Narrow deliverable: distinct branded authentication entry, not a claim of live AutoApply success.

## Scope
Anonymous users get a minimal high-contrast SmartPloy entry rather than an outage screen. Sign-in remains ZITADEL OIDC with the existing Authlib authorization-code/PKCE, nonce, browser-specific state cookie, account binding and HttpOnly session. Sign-up requests ZITADEL's documented prompt=create. Google routes through ZITADEL using its documented direct IdP scope, never a separate Google SDK or client. Both modes use original preapproved Google web button images, and Google links are enabled only after a valid operator-managed ZITADEL provider ID is configured.

## Reuse / copied / sanitized / adopted
- REUSED unchanged: galapoto/smartploy main at d4153ebc1e4187ff9c74120a187e059f18691f6e, files smartploy/oidc.py (existing PKCE, callback, cookies), smartploy/api.py (Authlib OAuth client), web/src/BrandMark.tsx (existing mark), web/src/App.tsx (existing account-bound loading and private session verification).
- COPIED unchanged: user-supplied signin-assets.zip, Web (mobile + desktop)/png@1x/light/web_light_rd_SI@1x.png and web_light_rd_SU@1x.png. Original SHA-256 values: 3842523b5707c960fbfb6c8d9e43bf04f143e5a3e72fc83bdaf91ffbdb2a1a18 and d7cb51060d2a0a0a856d4b42952ddc313fa1a83d1aa6b68313a0ec0b7a0040dc. Destination: web/public/google-signin-light.png and web/public/google-signup-light.png. Original Google artwork is not modified. Use per Google's official Sign in with Google branding guidance.
- ADAPTED: initial getSession 401 no longer auto-navigates; App uses this typed failure to display SignIn, while other authorized API paths retain existing redirect behavior.
- NEW: SignIn.tsx, signin.css, /auth/providers, ZITADEL-only trusted registration/provider options, tests and configuration wiring. New runtime dependencies: none.
- No external source-code port. REA not applicable: the authorized first-party source was readable. Apple HIG accessible focus/keyboard guidance, Google asset guidance, and existing Vitest/pytest standards applied as design/test references, not falsely described as executions of external skill programs.

## Provider activation / operator runbook
1. In ZITADEL configure and activate a Google identity provider, enable external login and self-registration as intended. Register the Google OAuth callback only with ZITADEL, not SmartPloy. Obtain its exact numeric IdP ID.
2. Add SMARTPLOY_OIDC_GOOGLE_IDP_ID and, only if custom org login policy requires it, SMARTPLOY_OIDC_GOOGLE_ORG_DOMAIN to private deploy/personal/env. Do not store secrets or Google OAuth credentials in the SmartPloy repo or frontend.
3. Run exact commit CI, web build (tsc/Vite), backend tests/test_oidc.py, two-account sign-in and signup browser verification, then guarded deployed-SHA and public release-evidence checks. Confirm exact Google redirects, not merely rendered buttons.

NOT VERIFIED until tested: Google IdP activation in ZITADEL, real new-user registration and external account linking, private two-user browser acceptance, production deployment, and any real employer application submission.
