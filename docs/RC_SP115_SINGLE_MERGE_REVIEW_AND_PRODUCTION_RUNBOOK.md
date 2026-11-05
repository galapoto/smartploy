# SP115 — One-review SmartPloy CV-first application release candidate

**Status:** INTEGRATION_SOURCE_REVIEW_HOLD; source only. **No PR merged, no
production deployment, no real employer submission/receipt inferred.**
Date: 2026-11-02. Owner: SmartPloy / `galapoto/smartploy`.
Base: `main` at `804747bd9f01f999f9e806dcf96459bb215bb8f1`.
Integrated source head: `d98881296081007c8e70447982cce67e847dcb94` (SP114).

## Why an integration candidate

Six independently tested, review-ready dependent PRs remain OPEN, with no
recorded independent reviews or merge approvals. Their source content is
linear and `main...SP114` is ahead 143 commits, 54 changed paths
(9,034 lines added / 145 removed at the pinned source head).

| Existing owner-review item | Source SHA | Acceptance |
| --- | --- | --- |
| #275 CV-first application and private revision-locked documents | `034cc9e0d6a9cd1b9b9cde6723df0175405ced80` | Exact source retained |
| #276 CV-read fail-closed / preserved drafts | `a7234a502eaffbc3bdc563cdc9db844dd4329967` | Exact source retained |
| #277 ObumAI-derived local Playwright assistant & pairing | `59e993f68d9676f9438c823c84e060b834ff0b41` | 5/5 CI, run [41443383373](https://github.com/galapoto/smartploy/actions/runs/41443383373) |
| #278 exact reviewed CV PDF attachment | `0f9513b4aece9567fa437b3eb7bdae0d2fe849bf` | 5/5 CI, run [41448667066](https://github.com/galapoto/smartploy/actions/runs/41448667066) |
| #279 Chrome-origin receipt observation reused in Playwright | `a86e16b6016f486b00f023f7818f39165915a291` | 5/5 CI, run [41465055281](https://github.com/galapoto/smartploy/actions/runs/41465055281) |
| #280 existing Chrome question policy reused for applicant-reviewed text answers | `d98881296081007c8e70447982cce67e847dcb94` | 5/5 CI, run [41468194247](https://github.com/galapoto/smartploy/actions/runs/41468194247) |

**Decision:** Offer ONE combined release PR directly to `main`, pinning
exact original content with `docs/SP115_SOURCE_INVENTORY.json` and
`scripts/verify_sp115_integrated_source.py`. If independently approved,
merging the rollup can replace six sequential review/merge operations
without rewriting the source or bypassing any final release gate. **Do
not merge the rollup AND its ingredient PRs as separate releases.**
Keep original PRs as traceability until the integration PR is accepted;
the reviewer chooses one merge route and confirms the same source.

## Exactly what the candidate does

**Signed-in CV → mode choice**. Current CV is read with account-bound OIDC;
a failed private read does not mean there is no CV. The start screen clearly
offers Manual, Assisted and Automatic, initially locked until a verified CV
exists. Saved drafts are owner-private, reopen after reload, retain the
previous sidebar and support dark/light modes.

**Manual**. Choose a verified job, use its private job-specific CV and
letter editor and download exact revision-locked PDF/DOCX and complete
application ZIP. Applicant sends personally. No employer action occurs
on draft preparation/download.

**Assisted**. Same reviewed CV/letter plus locally installed Chrome
companion or ObumAI-reused visible Playwright browser on applicant
`127.0.0.1:48741`. One-time pairing, exact employer/field verification,
applicant-approved ordinary fields, separately reviewed CV attachment
with SHA-256, applicant-authored eligible text answers, protected
questions/manual terms/visa/salary/EEO, and separate post-submit
read-only employer page observation. Browser evidence remains
`browser_observed_unverified`. Browser never clicks final Submit.

**Automatic**. CV-matched opt-in private draft preparation, owner-scoped
application agent and tracked review queue. A first-party **foreground**
AutoApply batch is limited to up to three individually reviewed
Lever/Ashby jobs only where independently authorized employer API
rights exist. The applicant explicitly confirms each exact employer,
contact detail and document before a once-only server-atomic transfer.
Employer ACK or uncertain is distinguished. **No general unattended
job-board auto-submit, CAPTCHA/MFA bypass, unapproved email send, fake
receipt or indefinite retry exists.** This is not full unsupervised
AutoApply.

## Immutable, read-only source gate added for the integration PR

`docs/SP115_SOURCE_INVENTORY.json` contains the main/source SHAs, six
historical PR heads, release HOLD booleans and 24 critical original
Git blob IDs: app navigation, master CV, application studio, local
Playwright and original Chrome rules, backend identity/handoff,
AutoApply synthetic contract and release scripts.

`python3 -B scripts/verify_sp115_integrated_source.py`
reconstructs each Git object SHA1 from local bytes, checks path
allowlisting (no path traversal/symlinks), requires all 24 exact inputs
and **rejects any false production/automatic-submission/REA claims**.
This is a source-equivalence test and prints only boolean results;
it never reads applicant files, credentials or production data.
`tests/test_sp115_integrated_source.py` tests positive and hostile
cases including changing one byte, missing a file, traversal paths,
fake release GO and fictitious employer verification. Changes to
any pinned source file require a consciously re-reviewed inventory
and a new exact-head CI receipt.

## Release acceptance — order is mandatory

1. Confirm the rollup PR is based on the expected `main` SHA and
   contains all source/negative tests from PRs #275–#280. Review *full*
   application journey, security, privacy and permissions; get
   independent code/privacy sign-off. The manifest does not substitute
   for that review.
2. Check **all five** GitHub Actions jobs on the exact rollup HEAD,
   including real synthetic Chromium, browser E2E, PostgreSQL, TS/Vite
   and Docker/Caddy source parity, with no skipped required gates.
   Synthetic CI alone does not prove real employer acceptance.
3. Run the original **native Woodpecker/ObumDelivery** acceptance
   required by the deployment owner; a GitHub Actions green cannot
   silently replace that approval.
4. Obtain explicit owner/Director release GO for the exact immutable
   *post-merge main* SHA. Confirm approved employer integration rights
   and OIDC policy; never infer rights from the public ATS or a CV.
5. Independently authorize the production operator to run the repo's
   ORIGINAL server-side `deploy/personal/scripts/deploy.sh` using
   that exact approved main SHA and `SMARTPLOY_PRODUCTION_IDENTITY_MODE=oidc`;
   no release may deploy an unreviewed PR SHA. Reuse its preflight,
   exclusive operation lock, recovery backup and rollback procedure.
   **This source-only PR does not run those commands.**
6. Demand post-deploy `deploy/personal/scripts/release-evidence.sh
   --online`, with running API/worker/web image parity, local and
   public front-end sha parity, exact Chrome and Playwright ZIP/checksum
   parity, source worker/agent checks and public signed-out private
   API denial. A healthy `/healthz` alone is insufficient.
7. Signed-in consenting applicant live acceptance: see the CV
   entry and all three mode buttons *immediately after login*;
   verify saved CV/letter edits and exports; show the three distinct
   completion paths; pair a real local helper only if applicant
   consents and employer allows this workflow; verify no silent
   application send and no provider ACK without a real provider
   receipt. Check sidebar, complete logo, Finland banner, mobile
   layout and readable dark/light mode. Keep all local PII out of
   review artifacts and screenshots.
8. Only after each gate, record signed operator/owner evidence of the
   exact deployed SHA and provide rollback receipt. If any step fails,
   leave previous production running and report the real blocker.

## REA/reuse decision (REA-FIRST-001)

**REA_BLOCKED** in prior SP110–SP114 work: official
`morluto/rea` pinned and source-inspected, CLI/MCP unavailable on the
coding host, npm acquisition DNS failed. No REA CLI trace is asserted.
Actual reuse: first-party ObumAI Playwright visible Chromium/fill
primitives; original SmartPloy Chrome extension inspection/field,
question/PDF/receipt rules; SmartPloy owner-scoped API, document
renderer, ATS partner rights, existing test/CI/release scripts. SP115
adds only the release-candidate source inventory, small offline
verification and review runbook. No unrelated binaries/site content
copied. Actual time savings: **unknown**.

**What remains blocked:** independent review/owner GO, native CI,
postmerge main SHA and backed-up live OIDC deployment, authenticated
first-party browser acceptance and any employer-granted final action.
No permission to release or falsely claim fully unattended submission
is conferred by this file.
