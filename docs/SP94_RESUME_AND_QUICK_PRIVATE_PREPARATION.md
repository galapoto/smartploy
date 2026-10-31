# SP94 — Resume existing applications + one-action private AutoApply preparation

## Why this increment
SP93 (released at `acf6908d03f0`) restored sidebar and visible
Manual / Assisted / Automatic modes, but a saved application was still
difficult to finish after reloading the site:

1. `App.tsx` holds `flowMode` only as React state, initially `null`.
2. `ApplicationStudio.tsx` showed its Assisted walkthrough **only**
   for `mode === "assisted"`, and rendered the already-implemented
   `AuthorizedAutoApplyBatch` **only** for `mode === "automatic"`.
3. On a fresh browser session, the owner could see private drafts in
   My applications but could not directly resume those completion
   controls without backing out to the CV flow and choosing a method
   again.

Separately, automatic preparation previously required a user to find
a shortlist control, select safe role-title matches, then locate a
second button. The private preparation and per-job agent loop already
existed; it did not need to be rebuilt.

## Implemented
- **My applications → Resume method:** if the signed-in account has a
  saved draft, render an explicit Manual / Assisted / Automatic choice.
  The controls call the existing `setFlowMode` state in App. No method
  is silently persisted or inferred, and no external action occurs.
- **Assisted after reload:** selecting Assisted reveals the already
  working reviewed CV/letter, browser companion, employer posting and
  outcome actions for the exact selected saved draft.
- **Automatic after reload:** selecting Automatic reveals the existing
  authorized employer batch eligibility check for the account's saved
  drafts. The existing employer API rights, fresh reviewed documents,
  one-shot attempt reservation and explicit final approval still apply.
- **Quick private AutoApply:** on the CV-matched Apply page, a new
  one-action button prepares up to 15 already loaded, source-current,
  role-title-aligned, safely linked vacancies. Before any private POST,
  a native confirmation lists *each exact job title and company* and
  warns that no employer will be contacted.
- The quick path uses `addCVShortlist`, `visibleCurrentKeys`,
  `onPrepareSelected`, existing identity/CV revision guards,
  per-job agent and idempotent workspaces, stop/retry behaviour.
  No second application engine, fake job signal or external send path.

## Scope and safety
- A **private draft is never an employer submission**. Saving a private
  draft does not approve a browser form send or ATS submission.
- No background employer sends, bypasses, inferred employer rights or
  retries after uncertain provider outcomes.
- Saved drafts remain server-owned and account-scoped; changing resume
  method is presentation-only. No browser storage of CV contents.
- Candidate matching is a retrieval suggestion, not a qualification
  verification. For quick selection, a role-title match, current
  source and valid original employer URL are mandatory.
- Every actual ATS submission still requires documented independent
  employer API permission, a reviewed exact document, a fresh review
  receipt and a separate user-approved one-shot POST; blocked jobs
  remain Assisted/Manual.
- UI follows SmartPloy's own existing Career Atlas style and preserves
  the full sidebar.

## Release acceptance
- Frontend tests: no-mode saved-draft controls, Assisted and Automatic
  reentry, quick consent cancellation, exact safe shortlist selection,
  no automatic employer POST.
- Chromium production frontend fixture: prepare a real private draft
  through the synthetic API, then reload, open My applications,
  select Assisted and Automatic, verify the review queue remains
  unchanged and no employer acknowledgment was fabricated.
- CI: backend, web, Chromium, isolated OIDC Compose and exact-checkout
  evidence must pass before merge. Public production parity plus
  `release-evidence.sh --online` are required after operator deploy.
