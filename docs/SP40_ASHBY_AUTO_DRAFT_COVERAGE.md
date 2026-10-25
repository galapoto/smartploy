# SP40 — Finnish Ashby jobs enter opt-in private AutoApply draft preparation

**Plan:** SP21 P0-B CV-first AutoApply preparation and Agentic SmartPloy Gate 1.
**Baseline:** SP39 merged `main@b061dd50f66b3dc9308cc27728e72acb7b72e891`.
**Source change date:** 25 October 2026.

## Real core gap

SP20 already deployed the *source code* for Ashby's read-only public board adapter
and added Finnish Ashby employers in the 29-board portfolio. However,
`_approved_source_for_auto_draft` in the original SP15j private shortlist
explicitly allowed Lever, Greenhouse and SmartRecruiters only. Consequently an
approved, freshly observed Ashby posting could appear in CV-first search but
always counted as `unverified_source_skipped` and never received an opted-in
background draft or optional per-job Agent Zero case.

## Reuse-first source integration

**Existing products reused without replacement:**

1. SP20 `PublicATSAdapter` /`AshbyAdapter` and its approved read-only
   `direct_employer_ats/api` source policy, listed-only and explicit Finland
   location filters.
2. SP15j `prepare_profile_shortlist`, original job ledger, preferences
   opt-in/revocation guard, `score_candidate`, approved profile facts,
   owner-scoped CV, existing idempotent workspace and optional SP33 Agent Zero
   creation, default-off worker.
3. Existing verified-source age limit (48 hours), unchanged-job recheck under
   the account's opt-in lock and no-external-action result contract.

**Only newly written:** one narrow Ashby provenance predicate, a branch in
the existing source trust gate, real mocked Ashby HTTP → original normalizer →
private draft integration tests and negative/race checks. No new source adapter,
crawler, database tables, model provider, dependency, web identity, auth
permission or submission routine.

## Safety contract for Ashby auto-draft eligibility

The original `source_class=direct_employer_ats` and `source_mode=api` must
agree in the stored job and candidate metadata. Additionally, the sole
source ID must encode the actual Ashby board tenant; source_details must carry
`provider=ashby` and the same tenant; source terms must be approved; original
board URL and application URL must both be HTTPS on the exact
`jobs.ashbyhq.com` host, the original posting must be under that board and the
application URL must resolve to the same posting or its `/application` path.
The stored external source ID must be the same SHA-256 of the canonical board
posting URL produced by the original SP20 adapter.

Mixed-origin merged records, changed tenant/job, malicious offsite application
targets, missing provider metadata, unlisted/outside-Finland feed entries,
stale verification and late changed application destinations remain blocked.
No candidate CV is forwarded to Ashby or ObumAI; no employer is contacted.
A public job listing is **not** authorization to use the employer's submit API.

## Core tests and release gates

The synthetic board fixture exercises the *real existing Ashby GET adapter*,
which discards one unlisted and one foreign job, then normalizes the Finnish
posting into the unchanged private shortlist worker. One eligible opted-in
applicant gets precisely one draft, a second pass creates no duplicates, and
the saved workspace carries `may_submit_to_employer=false`.

Additional tests block altered external ID, wrong board, wrong job, changed
application host, HTTP downgrade, source metadata changes, mixed-source IDs,
withdrawn source review and a race in `job_repository.get` under the original
revocation lock.

Run full PR-head GitHub CI (Python/Postgres + Node/React + Chromium + Docker
smoke + exact source receipt). Merge only on green, and rerun for immutable
merged-main SHA. Independent **native Woodpecker ObumDelivery** exact-SHA
qualification, guarded OVH deploy, source freshness and signed-in ZITADEL
two-account acceptance are still required to claim production delivery.

`SMARTPLOY_BROWSER_FINAL_SUBMIT_ENABLED` stays default OFF. The result is
**automatically prepared private review-required drafts**, never unattended
employer applications or provider acknowledgments.
