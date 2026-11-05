# SP113 — Original Chrome receipt observer in SmartPloy Playwright

**Date:** 2026-11-02
**Branch:** `feature/sp113-playwright-reviewed-receipt-20261102`
**Dependency:** SP112 PR #278, then PRs #277 → #276 → #275.
**Maturity:** source in review; **NOT deployed or an employer submission**.

## One complete Assisted flow without a second browser engine

SmartPloy already has:

- a saved/revision-locked job-specific CV/letter editor and PDF exporter,
- an exact, short-lived, approved `smartploy.browser_handoff.v2` packet,
- the ObumAI-derived visible persistent Playwright Chromium browser with
  reviewed field fill (SP110/111) and separate exact CV attachment (SP112),
- **an existing read-only Chrome companion receipt detector**
  `browser-companion/popup.mjs` `inspectReceipt(expectedApplicationUrl)`
  and the owner-scoped `importBrowserReceipt` API with the server-side
  `smartploy/browser_receipt.py` validation.

**SP113 directly reuses these implementations.** The deterministic
`web/scripts/package_playwright_assistant.py` build reads the actual
Chrome companion receipt function and extracts it into the approved
`receipt-inspector.js` bundle entry. No second page parser or receipt
heuristic is introduced: exact hosted ATS job, confirmation phrase,
reference, sanitized URL, stable SHA-256 page-text digest and live Submit
button exclusion are unchanged from the original browser companion.
A byte-for-byte extraction test prevents silent drift. The JS is
evaluated read-only in the existing local Playwright Chromium session.
No fresh platform account, persistent storage, remote browser bridge
or permission to submit to an employer is created.

The applicant still personally clicks Submit in the real visible
employer browser. Only afterward, in Application Studio:

1. **Observe employer confirmation (read-only)** is a separately
   confirmed action. The helper scans only same-provider browser
   pages and returns the original Chrome companion's bounded reference
   and sanitized confirmation-page URL/hash. It never returns page
   text, cookies, CV, user fields, full HTML, or a browser secret.
   An ambiguous, incomplete, wrong-job or still-submittable page
   returns no confirmation.
2. **Save unverified observation to SmartPloy** requires a SECOND
   explicit confirmation. A signed-in OIDC session and the exact saved
   document revision are checked; the existing owner-authenticated API
   `POST /api/v1/application-workspaces/{id}/browser-receipt` validates
   the schema, job identity, document SHA, reference, page hash and
   freshness, then persists `browser_observed_unverified` only.
   A POST is single-attempt in the UI; an uncertain outcome requires
   a read-only refresh, never an automatic POST replay.
3. The original Application Studio state and receipt display receive
   the same `BrowserObservedReceipt` object returned by the API.
   Existing manual receipt import remains available (Chrome extension
   fallback), and employer claim/anti-duplicate locks are retained.
4. The user may separately, **after actual personal receipt checking**,
   report an applied status through SmartPloy's existing workflow.
   Browser-observed evidence never updates an independently verified
   employer-submission count.

### State and privacy boundaries

- Local helper listens only on `127.0.0.1:48741`; exact-origin
  CORS/Host, memory bearer, no cookies, no PII logs. New
  `/v1/observe` is explicitly confirmed and read-only.
- `BridgeState.observe` requires the unexpired original 15-minute
  packet and exact reviewed job, returns a **single** positive
  observation, does not call employer APIs and never retries Submit.
- Observing an existing reserved/uncertain employer attempt is permitted
  because it is read-only. That reservation still BLOCKS new form
  filling, CV transfers and all unauthorized final clicks.
- The frontend independently checks current OIDC subject and
  job/CV revision before the observation and before the private
  receipt import. Browser-packet and helper credentials remain
  in temporary component memory; no general clipboard/URL forwarding.
- This observer executes in Playwright's page execution world; an
  employer page can influence its DOM. Therefore its reference is
  strictly an **unverified browser observation**, not a provider-
  signed or independently verified acknowledgement.
- A missing/ambiguous reference, changed job, active Submit button,
  stale packet or user mismatch fails closed. No CAPTCHA/MFA,
  identity challenge, employer account or legal consent is bypassed.

## Evidence

- `tests/test_playwright_assistant.py`: archive contains only the
  pinned source, original receipt inspector function, SHA-256 manifest,
  original source parity and deterministic byte-identical ZIPs.
- `tests/test_playwright_assistant_chromium.py`: actual Python
  Playwright in network-blocked Chromium synthetic employer fixtures
  tests exact posted job's reference, stripped tracking query/fragment,
  live Submit rejection, unrelated job rejection, missing reference
  denial and zero external requests.
- `tests/test_playwright_local_bridge.py`: original local server,
  exact token/CORS, explicit approval, packet expiry, one positive
  evidence per session and no employer/SmartPloy submission.
- `web/src/LocalPlaywrightAssist.test.tsx`: separate consent
  for observation and owner-scoped receipt saving, reserved-ledger
  read-only observation, no automatic import when evidence missing,
  no second state-changing import.
- Original backend receipt and existing extension E2E tests retained;
  existing Docker/Caddy source-to-served ZIP, OIDC and release gates
  remain required.

## REA and release

Official `morluto/rea` was reviewed from original source in SP110,
but executing REA CLI/MCP remains **BLOCKED** on the coding host. SP113
copies no protected third-party source and directly extracts the
first-party approved Chrome inspector; no fabricated REA analysis or
savings estimate is claimed. `savings=unmeasured`.

**PRODUCTION HOLD:** independent privacy/security review, exact
head CI, acceptance of original Chromium and Chrome companion
parity, separate approval/merge #275 → #276 → #277 → #278 → this PR,
native Woodpecker/ObumDelivery evidence, immutable backed-up
operator-initiated OVH deployment, live signed-in user/consenting
employer confirmation acceptance and preserved rollback. A green
synthetic test does not demonstrate a real job submission or receipt.
