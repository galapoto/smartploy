# SmartPloy AutoApply — delivery and reuse-first plan

_Updated 21 October 2026. A source-code branch is not a production release._

## Product outcome

1. A signed-in person can choose **general** or **personalized** IT search.
2. Under **personalized**, the user approves career facts, specifies target job titles
   and explicitly opts into private automatic draft creation. They can revoke it
   at any time without giving employer-submit permission.
3. The **existing** source worker retrieves public employer postings from
   operator-configured read-only ATS adapters; source health and freshness
   remain independently auditable. The five-employer Finland pilot is now wired
   into **new-installation `deploy/personal/env.example`** through the existing
   immutable image-local source file. Existing operator environments remain
   unchanged and live production polling is still unverified.
4. The **existing** matcher compares the chosen titles/locations/languages
   against current jobs and checks qualification gaps using only approved facts.
   Private CV and letter drafts are saved to the original owner-bound
   application workspace. Consent revocation races are serialized, repeated
   runs do not create duplicate application workspaces, and user mistakes are
   surfaced with actionable guidance.
5. Employers receive NOTHING at the draft stage. Real final application
   submission is a separate action requiring applicant review and exact
   employer/partner authorization, durable one-attempt reservations and a
   verified provider acknowledgment. No false submitted counts.

## Reuse inventory and measured status

| Capability | Original code reused/adapted | New glue and test evidence | Current stage |
| --- | --- | --- | --- |
| Public job ingestion | `smartploy/sources/public_ats.py`, `public_ats_polling.py`, `storage.py` and operator-curated `config/finland_public_ats_pilot.json` | Source health / source age policy reuse; new-install env points to reviewed pilot | Worker configured for new installs; OVH polling **not verified** |
| Search and matching | `search_preferences.py`, `scoring.py`, owner preferences storage | Conservative per-owner shortlist | Implemented in stacked review branch |
| Approved career evidence | `profile_storage.py`, `cv_storage.py` | Required approved facts; no invented credentials | Implemented in review branch |
| Private application documents | `application_workspace.py`, `application_workspace_storage.py` | Immediate first opt-in scan and account-safe navigation | Implemented in review branch |
| Continuous worker | `worker_runtime.py`, `worker_schedule.py` | Fair per-account scans, revoked-account guard | Implemented; production scheduler not verified |
| Source failover/currentness | Existing `last_verified_at`, `last_seen_at`, polling failure retention, source policy provenance and merge deduplication | 48-hour auto-draft freshness gate plus reviewed-source-only provenance gate and owner-bound rechecks | Implemented in review branch; current CI required |
| Employer final submission | Existing SP15e–h durable reviewed Lever partner path | No additional generic ATS auto-clicker | Employer rights/live acknowledgment **not verified** |
| Identity / user privacy | Existing first-party ZITADEL OIDC + same-account/CSRF guarded API | Use original strict `runPrivateMutation`, no second auth | Live production sign-in **not verified** |

**Licensing and speed discipline:** Search internal ObumAI/SmartPloy code
before writing, reuse safe and tested code instead of duplicating it,
and check upstream GitHub/YouTube/TikTok projects and licenses before
importing any third-party implementation. Modifying a restricted-license
codebase does not make its license permissive. This phase added **no new
third-party library** or independently invented crawler, authentication
provider, model service or employer submitter.

## Priority delivery backlog

- **P0 — freshness and honesty:** Insist on a recently verified source
  timestamp for any automatically created draft; show explicit source
  refresh guidance; validate keyword-only roles on the original settings
  UI. Code implemented on PR #173, pending final exact-head CI.
- **P0 — real employer listings:** The new-install example uses the
  existing reviewed `config/finland_public_ats_pilot.json` as the
  worker's immutable source file. On **existing** installations, use
  existing `scripts/configure_finland_ats_pilot.py` to stage reviewed
  sources without overwriting operator env, let the existing worker poll, then
  run **existing** `scripts/check_ats_readiness.py --require-healthy
  --require-jobs --require-fresh-hours 48` on the actual worker. Capture
  aggregate source/job counts, timestamps, and exact deployment SHA,
  never private env values. Current live results unknown.
- **P0 — review-first usable applications:** Verify a real signed-in
  ZITADEL account and a second independent account, search preferences,
  direct first scan, uploaded CV and evidence review, accurate draft
  documents, opt-out, CV erasure and account isolation.
- **P0 — consolidate review branches:** SP15j #173 is the chosen private
  draft path. Compare it with #169/#171/#172 before merging; avoid the
  duplicate SP16 preference table/matcher and duplicate migration 024.
  Keep final-submit review guards, employer rights and provider
  acknowledgment intact. Resolve divergent branch stacks before main.
- **P0 — release gate:** Require green exact-source GitHub tests **and**
  separately trusted native ObumDelivery SHA evidence including a
  negative control; human review of high-risk auth/provider changes;
  verified main merge, configured migrations and Compose, OVH source
  revision, live first-party sign-in, job refresh and draft save.
- **P1 — actual first employer application:** Secure documented employer
  Lever partner rights and a real applicant's explicit final review,
  submit one approved standard-form job through the existing exact
  partner API once, require provider-issued applicationId, and record
  it durably against the original workspace. Without employer rights,
  do **not** transmit or call it applied.
- **P2 — wider ATS coverage:** Evaluate each employer's documented API,
  signed form/schema, requirements and permissions. Reuse approved
  adapters and bridge code; implement missing forms only when permitted,
  with race/duplicate/failure tests. Do not promise unrestricted
  unattended final submission.

## Evidence to produce after each implementation run

Report the **specific source path**, original code/commit or external
licensed code reused, truly new logic and why it was missing, exact
commit and PR, Python/React/browser tests, CI job and conclusion,
native ObumDelivery result if available, deployed main/OVH SHA if
available, live source counts and actual employer acknowledgments if any.
Use **Done / In Progress / Not Started / Blocked** for the whole system.
A synthetic browser test, Docker build, GitHub CI pass, or draft worker
registration is not proof of live OVH service or real application submission.

## Current baseline (not production)

- Main: `d0ebe59a576f7814c7c3ecb5bc64b104afbf16b1` at last check.
- Active stacked PR: https://github.com/galapoto/smartploy/pull/173.
- Previous verified source CI:
  https://github.com/galapoto/smartploy/actions/runs/39463552450
  (726 Python, 104 React, 32 Chromium; 5/5 successful, synthetic only).
- This run: freshness logic `39b7ebf`, Python regression `0d2861d`,
  UI and consent fixes followed; the latest exact SHA and test status
  must be read from the PR and Actions, not inferred from this document.
- No evidence yet of new code on OVH, of native ObumDelivery approval,
  of an active five-source live poll, or of a successful real employer
  acknowledgment. These remain blockers to the requested end-to-end product.
