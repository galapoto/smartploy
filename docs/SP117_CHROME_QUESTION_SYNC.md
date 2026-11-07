# SP117 — Chrome extension question memory sync (source-only review candidate)

**Scope:** Continuation of SP116's signed-in, owner-private employer question memory.
**Branch:** feature/sp117-chrome-question-profile-sync-20261102
**Dependency:** SP115 rollup PR #281 → SP116 PR #282 → SP117.
**Status:** SOURCE REVIEW / CI CANDIDATE, **not merged, not deployed**.

## Why this bridge instead of an extension network permission

The original Chrome companion uses **only** activeTab, scripting and storage:
no host permissions, background process, public credentials or endpoint tokens.
The server's SP116 question observation endpoint requires a valid *first-party
signed-in OIDC cookie*, same-origin CSRF metadata, expected account precondition,
exact owned workspace and current revision. A chrome-extension origin may
not bypass those requirements.

After reviewing the employer form (Lever, Ashby or hosted Greenhouse only), the
existing Chrome companion's **original** question classifier selects up to 12
eligible required/unanswered text prompts. No answer is copied, inferred or
submitted. The popup queues only sanitized prompts, identifier strings and
one-time review digests in Chrome **session** memory for at most five minutes;
it never stores CV text, legal consent, form answers, real employer URLs,
contact fields, application packets, authentication tokens or cookies.

The user returns to the **signed-in SmartPloy tab**, reopens the popup and
clicks **Sync eligible questions to my SmartPloy profile**. The new injected
first-party read/mutation function checks HTTPS exact allowlisted origin and
top-level frame, OIDC subject, exact first-party reviewed-packet endpoint,
the SP116 saved profile mode and the existing SP116 owner-bound
question-observation endpoint. No cross-origin fetch, new server endpoint,
widened extension permission or model execution is introduced.

- **Guided profile:** server reclassifies each prompt/identifier, remembers
  eligible prompts as missing, and retains any existing reviewed exact-answer
  data without overwriting it. Applicant later explicitly approves an answer
  in SmartPloy's original ApplicationProfilePanel; no answers are stored by
  the extension.
- **CV-only profile:** first-party server is not called to persist new prompts.
  The popup confirms no question has been saved. Existing CV-only Manual,
  Assisted and Automatic *draft* flows remain available with more manual work.
- **Unavailable/stale session:** no success claim; pending prompts expire
  automatically, and any retry is an explicit click, never a background sync.
- **Job-specific/sensitive:** current first-party classifier and the
  **independent** SP116 backend deny protected labels and identifiers. Safe,
  job-specific motivation prompts may be remembered as manual-only;
  automatic reuse of an answer is prohibited by the original server.
- **Submission:** no action in this bridge fills employer fields, uploads a CV,
  clicks Submit, grants partner API rights or asserts provider acknowledgement.

## Source reuse and REA

Reused original browser-companion/questions.mjs, popup.mjs and
page-review.mjs reviewed packet/first-party OIDC pattern, original
review-bridge.mjs hashes, SP116's already tested
POST /api/v1/profile/application-questions/observe, original
browser-companion deterministic allowlisted ZIP packaging, and existing
real tenant/CSRF guard. New code only implements the short-lived handoff and
self-contained first-party question mutation plus synthetic security tests.

**REA_BLOCKED:** official REA CLI is not available in this environment;
no claim of running REA or of quantified savings. No cloned, proprietary or
opaque source was imported.

## Review checklist

1. Review *all* changed files and dependency PR #282, not only SP117.
2. Confirm Chrome permissions remain exactly activeTab + scripting + storage;
   no unreviewed background script, content script, external origin or
   browser actor is introduced.
3. Check no answer, CV, contact field, employer URL, session identity or
   cookie crosses extension storage; only exact digest and prompt metadata.
4. Run Node Chrome companion tests, Python source-inventory gate, vetted
   production ZIP packaging, full Python PostgreSQL/OIDC, web Vitest and
   synthetic Chromium acceptance on the **exact SP117 commit**.
5. Independently re-review SP116's strict server-side restricted category
   classifier and OIDC same-origin account gates, profile erasure and
   concurrency; correct findings before any production rollout.
6. Once the full stacked source is independently approved, merge **one
   reviewed dependency route**, not both aggregate rollup and component PRs.
   Require exact post-merge main CI, native ObumDelivery/Woodpecker, owner
   Director GO, backed-up immutable operator release, live OIDC two-account
   checks and consenting pilot on supported employer pages.
7. Verify extension v0.6.0 ZIP installed fresh and separately verify
   Playwright path; **do not** assume a green synthetic test proves live
   browser sync or any real employer submission.

**Release controls:** production deployment approval=false;
automatic unattended employer submission=false; genuine employer acceptance
verification=false; independent review required; no auto-merge.
