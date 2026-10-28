# SP58 — Open the exact new AutoDraft application, not an unrelated older case

**Implementation date:** 28 October 2026 · **Baseline:** SP57 merged source `cc56463b88e8193fd2600376bc650ff876712497`.
**Plan subpart:** SP21 P0-B (CV → current job → private saved draft → exact review) and Agentic SmartPloy private case handoff.

## Concrete core defect verified in original source

SP56 fixed the *explicit selected-job batch* handoff. But the earlier opt-in Automatic IT drafts flow is separate:
`saveSearchPreferences` and the signed-in "Find and prepare matching drafts now" POST invoked `prepare_profile_shortlist`, which returned **only aggregate counts**. The React frontend navigated to Application Studio without the just-created `workspace_id`. Its existing list/selection fallback can therefore open a completely different, older private application.

The same scan could **create** a draft just before a candidate revoked auto-preparation. In that case `disabled_after_revocation` was displayed as a generic failure, concealing already-saved progress.

## Reuse vs new

**Reused first-party components:** PR #172/SP16's opt-in engine already evolved into main's `smartploy/auto_draft_shortlist.py`; current `search_jobs`, approved fact verifier, fresh ATS provenance, owner/revocation lock, original idempotent `PostgresWorkspaceRepository.create_or_get`, original unique opaque `kit-<SHA30>`, existing OIDC session and expected-user-ID/CSRF protection, original `ApplicationStudio.focusId`, SP56 front-end exact-case handoff, private Agent Zero and source worker.

**New glue only:** existing immutable result `AutoDraftSummary` can carry up to three **exact new** kit IDs when `include_created_workspace_ids=True`. The signed-in same-origin owner POST explicitly requests/returns them through `owner_review_handoff()`. Original `public_counts()` and the background worker's default scan intentionally never include IDs, CVs, employers or account details. This is not a new public GET, owner lookup or permission token. Existing React type+two entry points select only a structurally consistent, server-returned newly created kit, then open the original account-guarded Studio. Missing/contradictory legacy responses clear stale focus and ask the user to choose from My applications rather than fabricate a workspace ID. A partially completed run with later opt-out still exposes completed draft progress without restarting.

**No new ATS adapter, new worker, crawler, database migration, model call, employer submit, third-party dependencies or license-ambiguous imported code.** Additional external-repo reuse is unnecessary because the entire draft engine, authorization and editor already exist. A speedup factor is not measured.

## Acceptance and regression scope

1. Unit: genuine in-memory opt-in -> original new_workspace -> exact owner kit ID, default worker no PII, counts-only summaries, second idempotent run returns no *new* ID.
2. PostgreSQL: owner receives exact newly committed kit; second same-email signed-in identity cannot read it.
3. FastAPI synthetic OIDC HTTP: exact owner POST, wrong expected-user-ID cross-account request and bad origin fail-closed; no employer IO. The two same-email principals receive different private kit IDs.
4. React: first opt-in immediate scan focuses the exact new kit; direct rescan focuses the correct kit; contradictory legacy result never guesses old ID; successfully prepared draft before revocation remains reviewable; existing cross-account response discard.
5. Full exact-PR source CI + independent merged-main five-gate CI, including Python/PostgreSQL, React/companion, Chromium and temporary Docker. These are synthetic source verification, **not live site acceptance**.
6. Native `obumai/obum-delivery` project remains disabled pending isolated runner owner activation. OVH target still lacks a verifiable public `release_revision`, so operator-approved exact-SHA deployment, two-account authenticated live QA, current source freshness and genuine authorized provider acknowledgement are **HOLD**.

**Guarantee boundary:** This feature prepares truthful, locally reviewable drafts only. It neither contacts recruiters nor authorizes background employer submission. Existing Lever/Ashby one-shot partner gates still require genuine independent employer permission and an explicit user gesture. Generic unattended browser submissions remain incomplete.
