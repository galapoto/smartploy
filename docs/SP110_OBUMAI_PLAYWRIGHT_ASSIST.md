# SP110/SP111 — ObumAI-derived Playwright reuse, permissions and exact source

**Approved source of truth:** `docs/v4/SMARTPLOY_V4_PRODUCTION_FIRST_CONTRACT.md` §§4–7.

The runnable helper is **first-party adapted source**, not a separately licensed third-party plugin. Its immutable donor is `https://github.com/obumai/obumellm` at `d682da2582ebfa3f013cf37dc542384fe605f303`. See `browser-playwright/PROVENANCE.txt` for exact original file/blob/function mapping and destination code. The source license status at that exact snapshot is **NO LICENSE/NOTICE FOUND**; never describe it as MIT or Apache. The user's explicit current code-reuse authorization is recorded, but public redistribution still requires owner/legal reviewer clearance. The ZIP includes the same provenance notice.

## Acceptance ledger

- **PORT/ADAPT:** ObumAI `obumellm/browser/fill.py` selector and field matching; `obumellm/browser/live_session.py` visible Chromium context. No unchanged code.
- **INTEGRATE:** SmartPloy `browser-companion/logic.mjs` exact review/TTL/hash policy; `browser-playwright/assistant.py` and `bridge.py`.
- **NEW:** loopback pairing, one-use plan tokens, local HTTP route contract, TS React panel, deterministic ZIP packaging, negative tests.
- **TEST:** Python fake HTTP and real Chromium fixture + React and exact archive tests. No third-party employer contacted in CI; no production applicant claim.
- **NOT VERIFIED:** public local-network browser permission in real production Chromium on the user's computer, real ATS login, first-party hosted remote browser API/CDP, full application submit.
- **COPY unchanged:** none. **REA:** not used; no opaque binary recovery needed. **Licensing:** owner authorized internal first-party reuse, public package awaiting source/notice review.

## Boundary

The helper is currently applicant-local and pairs only through `127.0.0.1:48741` with one reviewed SmartPloy packet. It does not implement the requested hosted remote browser. The Cloudflare tunnel hostname and control/service contract must be verified independently before adding a hosted adapter. Never expose arbitrary CDP debugging ports or send credentials/CV bytes to public artifact storage.

**Required exit:** independent review on exact source, GitHub and Woodpecker CI success, authorized merge into `main`, OIDC OVH exact-SHA deploy, signed-in UI, one employer form completed and observed at review with correct documents. Automatic final send remains separate job-specific authority and receipt logic.
