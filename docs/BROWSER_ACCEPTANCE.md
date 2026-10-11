# Real-browser first-use acceptance

## Coverage and limits

CI's \`browser\` job runs Playwright **Chromium against a Vite production
build/preview**, not jsdom. All \`/api/v1/*\` and \`/healthz\` requests are
intercepted by synthetic, fixed fixtures. Screenshots may be downloaded from
the \`smartploy-synthetic-browser-evidence\` workflow artifact.

This verifies that a real browser renders the inline SmartPloy mark and its
favicon, displays a first-use choice, accepts General search without a CV,
switches modes using Settings, renders preference explanations without claiming
eligibility, isolates same-email account changes, and stays usable at mobile
viewport size during a simulated optional-model outage.

**These are not production login or real job/employer submission tests.** No
Cloudflare Access session, Obum Identity credentials, real CV, externally
retrieved job details, browser companion submission, or employer receipt is
used. CI cannot establish that the owner personally saw the correct logo
through the production Cloudflare cache or authenticated browser session.

## Run with local synthetic data

From \`web/\`:

~~~bash
npm install --no-audit --no-fund
npx playwright install --with-deps chromium
npm run build
npm run test:e2e
~~~

The test runner starts \`vite preview\` on 127.0.0.1:4173 and intercepts
API traffic. No running SmartPloy API or PostgreSQL database is required.
Browser screenshots are written to \`web/browser-evidence/\` and must not
contain real account data. The screenshots and Playwright HTML report
are uploaded in CI with limited retention.

## Separate owner-authenticated acceptance (still required)

After a reviewed production deployment, a human with the approved account must:

1. Visit \`https://smartploy.obumai.com/\` in a normal authenticated browser;
   visually confirm the turquoise/navy inline logo, tab icon and mobile layout.
2. With a **new test account**, choose General search without providing a CV,
   check that real current job cards appear and no qualification score is shown.
3. Switch to personalized mode; save title, keyword, languages and work modes;
   confirm the rankings and explanations. Save further edits in Settings and
   verify they persist after re-login.
4. Check with a second account that its private preferences, CV, drafts and
   documents do not reveal those of the first account, including same-email
   identity alias cases where authorized to test.
5. Inspect actual source freshness and 5/5-or-current source health, not the
   synthetic CI counts.
6. Follow \`docs/APPLICATION_ACCEPTANCE.md\` for separately user-approved
   application-document and browser-companion acceptance. Never treat a
   browser-observed receipt as independently employer verified.

Record observed date, exact deployed SHA, browser, mode, screenshot hash if
captured, and any failed steps. Do not move Cloudflare Access or OIDC policies
solely on the strength of this synthetic test.
