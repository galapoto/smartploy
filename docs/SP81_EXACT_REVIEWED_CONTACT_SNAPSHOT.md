# SP81 — Exact applicant-contact snapshot for one-job employer review

**Baseline:** SmartPloy \`main@0fc03d8b0236074d1fb6ab7606b0e94f8764ac7c\`  
**Priority:** Working-paper redesign issue #243, AutoApply controlled final-action route.

## Gap and decision

The existing 10-minute employer review stores the exact saved workspace
revision, CV+letter digest and deterministic CV PDF digest. Its read-only status
and readiness previously considered this review current by revision/expiry,
even if a previously approved phone, name, email, location or link changed in
the applicant's profile without modifying the workspace.

The real final-action gate rechecked the *current* contact fields, but not their
originally reviewed values. With a new matching field digest, a different
approved contact could previously be carried into a final send under an old
CV review. This slice closes that gap. No additional applicant data is sent
outside SmartPloy merely to record a review.

## Implementation

1. Reuse the exact existing \`_approved_contact\` and
   \`approved_fields_sha256\` algorithms, in one lock-protected helper shared by
   the review-intent writer and the final-action consumer.
2. Migration 029 stores \`approved_fields_sha256\` with the exact owner, job,
   revision, document and PDF digests in the existing ten-minute
   \`smartploy_employer_review_intents\` row. Existing review rows default to
   empty digest and fail closed for final action; the applicant must re-review.
3. Require the caller's reviewed contact digest in the signed-in HTTP review
   request, then compare it to freshly locked owner-approved facts *inside the
   original review transaction*. Independent final approval and atomic one-use
   claim check the stored review contact digest **again**.
4. A recorded review is considered current in \`GET submit-review-intent\`,
   \`final-action-readiness\`, \`partner-lever-readiness\` and
   \`partner-ashby-readiness\` only when the fresh server packet still matches
   the recorded document, PDF **and** contact digests. Stale reads return a
   stale review indicator, not a false "ready" signal.
5. First-party React Application Studio sends the contact hash alongside
   document/PDF hashes for both manual browser review and employer partner
   review. The signed-in companion verification also rejects contact drift.
6. Existing owner quarantine, one-use claim ledger, provider outcome
   reconciliation, independent rights and release controls are reused.

## Compatibility and privacy

- No new bearer approval, browser click permission or automatic employer
  submission is introduced.
- No raw applicant contact value is stored in this added column; it is a
  SHA-256 fingerprint of the existing approved form fields and saved letter.
- Existing limited internal non-submitting review fixtures with missing
  approved contacts use an empty digest, **never valid for final action**.
  Real user HTTP review requires the complete 64-hex digest and a valid
  approved name/email.
- An applicant who changes approved contact details must explicitly cancel
  or let the old review expire, then record a fresh review of the new package.
- Exact match still does not prove a real provider submission; official
  acknowledgement and employer rights remain separate.

## Required verification

- Real PostgreSQL schema/migration tests and approved-contact storage.
- Signed-in OIDC API test that changes an approved contact without modifying
  CV or letter: review status becomes stale, companion verification denies,
  attempted old review denies and no employer claim is reserved.
- Independent final-approval test: a *new*, otherwise valid fields digest is
  rejected against a previously recorded review, then succeeds only after
  explicitly cancelling and recording the fresh review.
- Existing AutoApply synthetic-provider acknowledgments, uncertain outcomes,
  per-account isolation and browser contracts all remain passing.
- Exact-head GitHub Actions suite + separate Woodpecker/ObumDelivery and
  operator-approved pinned release. No production action in this PR.

## REA / reuse

**REA_NOT_APPLICABLE.** All relevant first-party code, SQL, API and original
tests are directly accessible; no authorized opaque application, binary or
third-party implementation needed recovery. Reused existing review,
final-action, profile fact, SHA-256, account tenancy and Postgres semantics.
New code is a small shared helper, schema column, checks, and regression
tests. No new Python package, copied external asset or font. Engineering
time savings: **unknown** (no controlled baseline measurement).

**Status:** source implementation submitted for independent review; neither
a green CI run nor this file is proof of a live employer acknowledgment.
