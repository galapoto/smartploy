# SP110 — reuse ObumAI Playwright form filling in SmartPloy

Date: 2026-11-02. Branch: feature/sp110-obumai-playwright-assist-20261102.
Baseline: SP109 PR #276 head a7234a502eaffbc3bdc563cdc9db844dd4329967,
stacked above release candidate PR #275, NOT merged into main or deployed.

## User-facing behavior

Application Studio > **Fill the employer's form** now includes a second
download: **Playwright · local form assistant** and a short explanation beside
the retained Chrome extension. The static file
\`/smartploy-playwright-assistant.zip\` and checksum are compiled from exactly
the reviewed \`browser-playwright/assistant.py\` and \`INSTALL.txt\` sources,
not an untrusted dynamic install or a generic remote browser service.

An applicant who installs pinned Python Playwright and Chromium **on their own
desktop** can open an isolated visible Chromium session, navigate to a
personally approved Lever/Ashby/Greenhouse job form and fill only stable,
empty, ordinary fields after viewing the plan and typing
\`FILL REVIEWED FIELDS\`. The user still supplies a fresh authenticated
SmartPloy packet through hidden terminal input. It expires in 15 minutes.
The binary ZIP contains no CV or private applicant data.

**This is an optional LOCAL assisted form-filling slice, NOT completed
end-to-end unattended AutoApply.** SmartPloy does not run a Playwright agent
on OVH; the app does not automatically connect to an applicant's computer,
manage Playwright installation, authenticate employer services, submit forms
or upload CV PDFs from this runner. Existing Chrome Companion covers the
approved user-operated CV PDF attachment path. The browser runner never
clicks Submit, bypasses CAPTCHA/MFA, uploads a file, stores a CV, reuses a
normal Chrome profile, or makes an unapproved cross-site final action.
The applicant can manually finish or stop at any point. No server secrets.

## Precise first-party reuse (not another browser engine)

- **ObumAI \`obumai/obumellm\`** at pinned
  \`d682da2582ebfa3f013cf37dc542384fe605f303\`, files
  \`obumellm/browser/fill.py\` and \`obumellm/browser/live_session.py\`:
  adopted Playwright \`locator.fill\`, unique-selector/count/DOM-identity
  checks, visible \`launch_persistent_context\`, user review before writing,
  and the observe/fill/reobserve stopping model. Adapted as an independent,
  tiny one-file client to avoid copying ObumAI-only \`Settings\`, action-plan
  persistence, local AI, application-workspace storage and server credentials.
  The actual portable selection/filling primitives are in
  \`browser-playwright/assistant.py\`; they are not unused samples.
- **SmartPloy owner code** \`smartploy/browser_handoff.py\`,
  \`browser-companion/logic.mjs\`: existing v2 reviewed packet,
  approval-revision/expiry, exact hosted ATS URLs, contact aliases,
  prohibited metadata, local-only approved contact transfer. The Python
  adapter mirrors the extension's relevant safety rules and refuses changes,
  with Python unit tests and real Chromium fixtures. No new employer access.
- **SmartPloy \`web/scripts/package_companion.py\`**: reuse the deterministic
  static ZIP allowlist/checksum pattern, separately allowlisting just
  \`assistant.py\` and \`INSTALL.txt\`. The extension continues unchanged.
- **Playwright Python**: optional on the applicant's computer, pinned
  \`playwright==1.55.0\`. Not installed in the SmartPloy API, worker, Caddy
  runtime or production image. Verify Python Playwright package provenance
  and licensing independently before broader distribution; this ZIP ships
  no package binaries.
- Owner-directed reuse of accessible first-party repos. This does not claim
  ObumAI's source is third-party open-source licensed. No protected external
  program source, browser secrets or REA-generated decompilation is bundled.

## REA-FIRST-001 evidence and limitations

**REA_BLOCKED.** Authorized target: readable first-party ObumAI browser
Python and SmartPloy browser companion JS (no reverse engineering required
to inspect either source). Consulted REA's official \`morluto/rea\`
README at pinned \`93b8b82db70279e40f484114cff9dc1958dc14ee\`.
Tool availability check on this coding host: \`rea\` executable not
installed; official npm registry acquisition (\`npm view rea-agents version\`)
failed with DNS \`EAI_AGAIN\`. No REA CLI/MCP recording was run. No fake
REA trace or recovered pseudocode is asserted. Reused readable first-party
sources directly, per directive's non-blocking fallback. If official REA
becomes available, run static JS-application analysis only on this
owner-authorized repository and save evidence; do not analyze arbitrary
employer products or bypass consent/access.

Savings: **unknown** (no measured comparable scratch baseline). No vendor
model/source forwarding, employer credentials, dynamic third-party JS,
native binaries, or external REA tool supplied to the shipped archive.

## Privacy, browser authority and failure modes

- This runner validates the **real** \`smartploy.browser_handoff.v2\`
  privacy flags, revision >=2, time-to-live <=15 minutes, full reviewed
  contact field set, exact SHA-sized CV PDF fingerprint and HTTPS host/job.
  A packet is not a bearer authorization to submit anything.
- Only exact official hosted Lever \`/apply\`, Ashby \`/application\` and
  Greenhouse \`/{board}/jobs/{numeric-id}\` pages can receive a fill.
  Custom employer URLs, iframe-only forms, unexpected redirects, tracking
  queries, credentials in URLs, and changed job identity are denied.
- Safe planned fields must have an original unique input ID/name, remain
  visible, inside a form, enabled, writable and EMPTY, match the original
  label/type/autocomplete after every action and not be sensitive.
  Duplicate, disabled, readonly, prefilled, salary, visa, citizenship,
  consent, password, file, legal and unknown inputs remain manual.
- Every field write rechecks packet expiration, exact page URL and entire
  observed input identity; changed controls stop the remaining plan. No
  automatic retry on an ambiguous fill. A web page may transfer entered
  values immediately; the terminal warns before the sole explicit approval.
- Applicant packet is pasted through a hidden terminal prompt, not a
  persistent file or CLI argument; the runner prints field names only,
  never CV contents or approval tokens. The isolated temporary browser
  profile is removed at close. User handles login, MFA/CAPTCHA and PDF.
- Separate physical, real-account, consenting-employer acceptance and signed
  release evidence still required. Synthetic success is NOT proof of actual
  job submission, employer receipt, or successful sign-in in production.

## Executable tests and delivery

- \`tests/test_playwright_assistant.py\`: URL allowlist/off-host/credential/
  tracker denial, stale and forged packet denial, sensitive and duplicate
  field exclusion, deterministic ZIP, changed URL/DOM stop, no submit.
- \`tests/test_playwright_assistant_chromium.py\`: real Python Playwright
  Chromium against fully intercepted synthetic employer pages; verifies
  approved names/email/letter actually fill, sensitive and password do not,
  submit counter remains zero, dynamic fields stop the remaining plan.
- \`web/browser-tests/playwright-download.e2e.ts\`: real web preview serves
  true ZIP bytes and sidecar checksum, with no login or HTML SPA fallback.
- \`.github/workflows/ci.yml\` browser job installs pinned Python
  Playwright/Chromium only for test, not runtime.
- \`web/Dockerfile\`, \`web/package.json\`, \`web/scripts/package_playwright_assistant.py\`,
  \`deploy/personal/web.Caddyfile\`: reviewed static package and non-SPA route.
- Retained existing Extension, its ZIP/gates, employer final-action ledger,
  authorized partner endpoints and OIDC privacy controls.

**Feature status**: Source implementation; exact SHA CI and independent
code/security review are required before merge; post-merge main evidence,
operator-approved immutable backed-up deploy, live ZIP/checksum parity,
sign-in and applicant-controlled test are required before production claim.
**REA status**: BLOCKED on official tool installation, reuse evidence present.
**Full remote Playwright workflow/any-site AutoApply**: NOT STARTED in SP110;
requires separately reviewed browser service, identity/session handoff,
employer-specific permission and deployment contract.
