# SP75 — One-click CV-matched AutoApply shortlist and exact search-scope guard

Date: 30 October 2026. Baseline: `main` at `611b43879156828c90c6f10632b7efc3766e1d5b`.

**Plan subpart:** SP21 CV-first core P0, Agentic SmartPloy Gate 2 candidate-controlled private automation. Follow-on to SP69 (explicit method), SP70 (current job selection), SP71 (verified application outcome), SP72 (review queue), SP73 (employer claim reconciliation), SP74 (release parity).

## Core functional improvement

Previously AutoApply required clicking a checkbox for every vacancy, even when the server had already ranked multiple **current CV-derived matches**. Users could also change the search field after ticking jobs, leaving old canonical keys selected while results were replaced. A silent draft for an unseen posting is a real candidate-control problem.

SP75 makes the fast path **CV → choose AutoApply → Select CV-title matched jobs → inspect shortlist → explicitly Prepare applications & start agents → review per-job drafts**. There is still NO unattended employer submission.

- New **Select N CV-title matched jobs** action adds up to 15 already *loaded* server-ranked recommendations, preserving individually selected jobs and eliminating duplicate canonical keys.
- A suggested job must be `source_current === true`, in the `recommended` lane, have the existing server's `Job title matches ...` justification (not merely a skill/keyword in the body), and have a sanitized navigable employer link. This avoids automatically choosing unrelated driver's jobs containing Python/Power BI words. This is **not proof of applicant qualifications**.
- Each selected title/company is inspectable before preparation; users can uncheck individual jobs or **Clear selected jobs**. Suggestions do not create applications; the existing separate button still invokes the original owner-checked per-job create-or-get + Agent Zero tracking path.
- Searches use the existing **server-side full-ledger matching**, not the first N browser cards; the shortcut only selects the already *loaded* ranked page (40 per request), and accurately says Load more to include more. No invented job counts or hidden background crawling.
- Changing a search or hiding exploratory jobs immediately resets selection. The search input's debounce boundary, missing/invalid URLs, stale/unavailable postings and hidden jobs cannot start preparation. A search changed during an in-flight request stops the queue **after the current job** and the owner can review any durably created draft under My applications. CV/account/mode changes retain the original safety boundaries.
- The existing role-specific manual/assisted choices, partial-success and blocked-job retry logic, draft editor, one-use employer attempt ledger and per-job agent inbox are reused unchanged.

## Reuse vs new work

| Area | Existing authorized source reused/adapted vs new |
|---|---|
| `smartploy/cv_job_matching.py`, `search_preferences.py` | **REUSED UNCHANGED**: local CV signals, Finnish/English career matches, source-current job ledger, full-ledger ranked pages and honest qualification uncertainty |
| `web/src/ApplicationJourney.tsx` | **ADAPTED**: original selected job state, exact canonical keys, batch stop mechanism, account/CV scope, source-current cards, private preparation CTA and retry handling |
| `web/src/lib.ts::safeExternalJobUrl` | **REUSED UNCHANGED**: rejects malformed/credential/control-character URLs |
| `web/src/App.tsx::onPrepareSelectedJobs` and server create-or-get | **REUSED UNCHANGED**: up to 15 per-job, idempotent owner-bound draft and agent requests; no employer calls |
| `web/src/autoapplyShortlist.ts` | **NEW MINIMAL** pure selector and stale-visible-key gate; 0 new dependencies or APIs |
| `web/src/styles.css` | **ADAPTED** existing design system for one-button choice and candidate preview; responsive/keyboard focus |
| Vitest + Chromium synthetic CV and application tests | **ADAPTED/EXTENDED**: title-only strict shortlist, no driver keyword match, stale/invalid link, 15 limit, search debounce change, genuine private create-or-get and no employer send |

**REA decision: `REA_NOT_APPLICABLE`.** Inspected available first-party SmartPloy implementation and mandatory `AGENTS.md`. REA (morluto/rea) is primarily for authorized analysis of missing/opaque application behavior; this change has complete authorized React, API and matching source and requires no reconstruction. REA was not executed; no recovered code, external third-party code, license bypass or quantitative engineering speedup is claimed (`savings=unknown`).

## Acceptance/CI and no-send boundary

1. Exact-head tests: only current/role-title-recommended/safe-URL entries are one-click selected. Keyword-only driver title, stale and broader jobs must not join automatically. Duplicate entries and 15 max guarded.
2. React: selection button is **not** a submit; only explicit Prepare begins the original draft loop. Query input changes reset selected jobs **before** the 250 ms debounce; async job replacement cannot silently prepare earlier keys. An active batch stops before another job after source scope changes.
3. Playwright: fictional CV → AutoApply → one-click shortlist → visible chosen title → explicit private draft creation → My Applications with 0 employer acknowledgments. A changed query without preparation creates 0 drafts. No real employers or applicant data.
4. Original server still verifies source-current canonical key, owner and CV, and creates or gets original private workspace with agent. No automatic employer rights, KEHA activation, authorization or real final send.
5. GitHub exact-head five jobs and merged-main CI are **source/synthetic fixture tests only**. Native Woodpecker/ObumDelivery admission, independent OVH release, real signed-in account acceptance and per-provider employer rights remain separate blockers on [P0 issue #232](https://github.com/galapoto/smartploy/issues/232).

## Evidence ledger

- **DONE in source:** strict one-click shortlist helper + UI and search-scope guards + regression tests + this plan.
- **IN PROGRESS until verified:** exact-head CI, reviewed integration, merged-main CI.
- **BLOCKED externally:** actual OVH production release, Native Woodpecker repo enrollment, authenticated real CV journey, KEHA P67 production source, partner ATS final send rights.
- **Expected output:** every run reports exact tested SHA, reuse/adapted/new, passing/failing tests, app source vs production, and actual block reasons. No claim of automated employer submission.
