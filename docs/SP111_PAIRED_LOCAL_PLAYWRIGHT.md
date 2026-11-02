# SP111 — Pair the existing ObumAI Playwright browser directly from SmartPloy

Date: 2026-11-02. Implemented on existing
\`feature/sp110-obumai-playwright-assist-20261102\` (PR #277), **not**
a standalone new branch and **not** a production deployment.

## What now works in source

The reviewed \`browser-playwright\` ZIP includes \`bridge.py\`, a tiny,
explicitly launched Python-stdlib HTTP server listening **only** on the
applicant's own \`127.0.0.1:48741\`. It reuses \`assistant.py\`'s
ObumAI-derived Playwright persistent browser session, exact-host/job
inspection, safety/field mapping and \`locator.fill\`. It does not add a
server-side headless browser or second automation engine.

In **My applications → Fill the employer's form**, after saving a
reviewed job-specific CV/letter and generating the usual existing
\`smartploy.browser_handoff.v2\` packet, a new
**Connect my local Playwright browser** panel offers a complete in-page
handoff with no packet pasted into a terminal per application:

1. Install Python Playwright + Chromium once, run \`python bridge.py\` on
   the applicant computer. A one-use pairing code appears in the terminal.
2. Enter that code in SmartPloy's panel and explicitly approve sending the
   existing reviewed private packet **only to localhost**. A visible,
   isolated Chromium window opens the current exact employer posting.
3. Applicant finishes any login/MFA and navigates to the exact approved
   employer form. Click **Inspect current employer form** in SmartPloy.
4. The UI displays **field names, never approved private values**. Confirm
   **Fill reviewed fields once**. The local browser enters approved ordinary
   contact and letter text, no automatic files or final submit.
5. Applicant reviews the employer page, manually attaches CV/PDF, answers
   sensitive questions, reads terms and chooses whether to press the real
   employer Submit button. Click **Stop local browser session** or Ctrl+C
   to clear temporary browser profile and session state.
6. Restart the helper for a different job/new pairing; old tokens are never
   saved in localStorage, sessionStorage, URLs or server logs.

This is still **reviewed assisted filling**, not fully automatic background
application submission. The old terminal-only SP110 runner and Chrome
extension remain. The helper cannot be started by the website or browser
due to browser/OS security restrictions: a one-time local helper launch
is required. Chrome may deny Local Network Access even with correct CORS;
the UI clearly fails closed to the extension instead of secretly uploading
packets elsewhere. No login/password collection or CAPTCHA bypass.

## Reuse-first and REA

- Pinned first-party original: \`obumai/obumellm\`
  @ \`d682da2582ebfa3f013cf37dc542384fe605f303\`, files
  \`obumellm/browser/fill.py\` and \`live_session.py\`: visible
  \`launch_persistent_context\` and safe DOM fill, already adapted in SP110
  \`browser-playwright/assistant.py\`. **SP111 shares the exact
  \`start_visible_browser\` function** between legacy CLI and new bridge.
- Pinned SmartPloy original: \`smartploy/browser_handoff.py\`, existing
  OIDC owner-checked \`browser-packet\` API and original Chrome
  \`browser-companion/logic.mjs\` field safety. No new applicant/backend
  identity store, employer rights, CV renderer or browser session code.
- Bundles with original deterministic allowlisted Python stdlib ZIP
  package/checksum, existing frontend, Caddy static-origin parity and
  release proof checks (SP110). No remote code download in archive.
- Official REA \`morluto/rea\` @
  \`93b8b82db70279e40f484114cff9dc1958dc14ee\` was
  source-inspected during SP110. **REA_BLOCKED** on available coding host:
  CLI/MCP was unavailable and npm acquisition DNS failed. No recovered
  binaries/decompilation or tool-generated REA traces are asserted.
  Readable, authorized first-party code was directly reused;
  \`savings=unknown\` without measured scratch baseline. Do not use REA
  to inspect unrelated employer sites without authorization.

## Strict security controls

- \`bridge.py\` uses \`HTTPServer\` on 127.0.0.1:48741, accepts only
  POST and CORS preflight for exact allowed first-party SmartPloy origins
  only. Local Vite previews are deliberately excluded from production\n  helper access. Exact loopback \`Host\` prevents DNS
  rebinding. No cookies/CORS credentials. Hard request-body size limit;
  no URLs or raw packet values printed; \`Cache-Control: no-store\`;
  \`Access-Control-Allow-Private-Network\` only for trusted origins.
- Random pairing code expires in 30 minutes, locks after five bad tries,
  is usable only once, and never appears in HTTP responses. The helper
  issues a separate, random in-memory session token for subsequent steps.
  Frontend does a current OIDC-subject check before/after every action,
  and unmount drops the local bearer token. No account email-only identity.
- The backend reuses actual v2 owner-reviewed packet expiry (15 minutes),
  exact current document revision and approved-fields SHA-256; no
  user-controlled arbitrary external URL. Allowed destinations are exact
  hosted Lever, Ashby, Greenhouse; custom sites or unrelated job IDs
  denied. Original local helper browser identity/field checks still
  re-run before each write. A CAPTCHA/security challenge blocks filling.
- The applicant approves the **specific field names** before any fill.
  A fill burns the single attempt BEFORE browser mutation; uncertain
  network/DOM results stop, with no repeat action. No file upload, submit
  button click, blind next-step navigation, credential transfer, private
  model inference or background process. Employer pages can transmit data
  when fields change; explicit user confirmation warns of this.
- The local helper uses a new isolated temporary Chromium profile per
  run and destroys it when stopped. Never attaches to a user's normal
  Chrome login profile or reads system/browser cookies.

## Tests and release posture

Python:
- \`tests/test_playwright_assistant.py\` verifies original v2 packet,
  expiry, contact-hash and exact ATS safety.
- \`tests/test_playwright_assistant_chromium.py\` executes real
  ObumAI-derived Playwright filling against offline synthetic forms.
- \`tests/test_playwright_local_bridge.py\` verifies pairing lockout,
  token and exact origin/Host CORS guards via real loopback HTTP,
  private-field non-disclosure, one-shot action, DOM changes, stale
  packet rejection, stop/recovery.
- \`tests/test_playwright_release_gate.py\` plus existing Docker
  release checks enforce byte-for-byte source ZIP parity, real 404
  vs SPA fallback and sha256 checks.

Frontend:
- \`web/src/LocalPlaywrightAssist.tsx\` + \`localPlaywrightBridge.ts\`
  provide account-aware open/inspect/fill/stop with local-only \`fetch\`,
  no local data persistence, explicit consent and usable dark mode.
- \`web/src/LocalPlaywrightAssist.test.tsx\` verifies in-page interaction,
  OIDC account switch denial, private packet delivery only to loopback,
  no automatic submission, local network refusal and no retry.

**PRODUCTION HOLD**: Independent security/code review, exact current-head
CI (Python, web, real Chromium, Docker, read-only release receipt), native
ObumDelivery/Woodpecker acceptance, owner/Director GO, dependency merge
#275 → #276 → #277, merge SHA acceptance, approved operator rollback-backed
deployment, live origin/static ZIP parity and a consenting employer test
in an authenticated actual applicant browser are still required.
Do not count any synthetic auto-fill, local browser invocation or observed
employer page as a provider-acknowledged application.
