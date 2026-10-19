# SP15g — reuse-first implementation evidence: official partner review without clipboard

## Core user operation, not a reporting-only change

Before SP15g, the newly built SP15f REAL Lever partner API required an
**unnecessary browser companion packet copied to the system clipboard**
before the signed-in applicant could even record the required 10-minute
review. The official partner POST itself is SERVER-SIDE and never needed
the clipboard. This forced applicant contact/letter PII onto the OS
clipboard, broke mobile/no-extension use and obscured the separate
user-review vs final-submit steps.

After SP15g, for an individually rights-reviewed, configured, standard
Lever partner job:
1. Applicant opens the existing SmartPloy Application Studio and reviews
   CV/letter/contact and the linked employer form.
2. The EXISTING signed-in, same-origin partner readiness endpoint returns
   only bounded SHA-256 fingerprints of the already-approved PDF/CV/letter/
   contact, exact private workspace revision and 15-minute expiry.
   **No CV text, cover letter, email, phone, API key, session or bearer**.
3. The NEW "Record reviewed CV, letter and job (no submit)" UI action calls
   the ORIGINAL verified signed-in SP15c 10-minute review POST. It checks
   exact backend hashes and the existing OIDC same-origin expected-account
   header. It cannot contact Lever. Successful review triggers a NEW
   independent backend readiness lookup under the EXISTING
   verifyAccount/runPrivateAction boundary; never optimistically unlock.
4. Only if the server now verifies current owner, job, documents, approved
   contact, independent employer API rights, valid signed-in review and no
   previous claim does the EXISTING SP15f "Submit reviewed application..."
   action appear. The applicant still makes a DISTINCT final confirmation;
   the ORIGINAL SP15e short-lived final approval/atomic SP15a claim and
   existing Lever multipart POST/returned applicationId logic is unchanged.
5. Unsupported ATS keeps the existing browser companion and manual final
   submit. No new browser privileges or customer secrets introduced.

## Proof: source already built REUSED, and what was newly added

**EXISTS + RIGHTS + QUALITY → GAP → ADAPT:**

- Reused \`smartploy/browser_handoff.py\` original blob
  \`b735847a9b27517d766afb48dca1e1df62c3bf89\`:
  \`make_browser_packet\`, \`approved_fields_sha256\`,
  \`render_document\`, profile-approved name/email, actual job/source
  validity, deterministic approved PDF fingerprints. No second PDF
  hashing engine and no new PII persistence.
- Reused existing SP15c
  \`smartploy/employer_review_intent_storage.py\` original blob
  \`0e3cc79d0473961fc69662b6b149ab4a1b7b5052\`,
  and \`smartploy/api.py\` original SP15f blob
  \`5e703a51808e2ebe73b432becbc03272ead1f9af\`
  (\`/submit-review-intent\`, \`signed_in_employer_review\`,
  \`_partner_lever_ready\`). **Adapted** the last endpoint to
  reuse the EXACT already generated packet but return only cryptographic
  evidence when partner is genuinely configured, independent rights
  approved, posting/current document ready and no prior claim/receipt.
  No new submission-capable API endpoint.
- Reused existing \`web/src/ApplicationStudio.tsx\` original
  SP15f blob \`8dbe37673875254c462b532925b633a37241b202\`,
  \`web/src/api.ts\` original blob
  \`239c580009e148712dc69fc4732a6b210215ee34\`, existing
  \`recordEmployerReviewIntent\`, \`getLeverPartnerReadiness\`,
  \`sendLeverPartnerApplication\`, \`getSession\`,
  \`verifyAccount\` and \`runPrivateAction\`. **Adapted** the UI to
  share the existing reviewed-intent submission helper between browser and
  partner modes, and to use direct private hash evidence instead of
  \`copyBrowserPacket\`. Existing browser packet/extension unaffected.
- Reused existing real two-user PostgreSQL/oidc test fixture and mocked
  Lever provider in \`tests/test_employer_submit_claims_postgres.py\`,
  initial blob \`f5a62554b827a20583a6756431e7e8b509becb00\`;
  adapted it to demand redacted nonbearer hash-only GET, distinct
  account/rights/claim isolation, no actual GET/POST to Lever before final
  action. Reused Vitest/JSDOM original file
  \`web/src/ApplicationStudio.test.tsx\` blob
  \`cc4c46255d73c44f5daf4ec9adf448e01f0a8529\`,
  added clipboard-free UI, expiry/mismatch and exactly-once assertions.

**Genuinely NEW source/logic (minimal):** one small strict
\`LeverPartnerReviewEvidence\` TypeScript type, one private JSON
\`review_evidence\` response shape for an EXISTING route (not a bearer),
one \`freshPartnerEvidence\` UI guard, one \`recordPartnerReview\`
control that invokes the existing review mutation, and revised
in-place flow tests. No newly invented auth/adapter/database schema,
dependencies, external code or standalone package. No license
circumvention. Official provider transport from SP15f remains unchanged.

## Completion and release evidence

See the latest SP15g draft PR and exact commit recorded in the SmartPloy
acceptance issue for the final immutable SHA/CI run. **The previous
SP15f baseline already passed** Python/PostgreSQL 689, React 94,
Chromium 32 and companion Node 36 tests on
\`97c86b0db913ca4811e836cae6b49158cea10dc3\`.
New tests must verify no browser packet operation on the official
partner path, no PII in readiness response, no rightless evidence,
current exact workspace/revision, post-review private recheck, and
no two employer POSTs or false acknowledgments. A green GitHub
source check is NOT native ObumDelivery acceptance.

**Production HOLD:** No actual employer key, partner-form/consent
evidence, partner test account, native Woodpecker source+negative
probe, owner-verified OVH deployment, or genuine provider applicationId
has yet been independently verified. The source default still DENIES
external applications. A claim reservation or mocked provider response
is NOT a real job application.
