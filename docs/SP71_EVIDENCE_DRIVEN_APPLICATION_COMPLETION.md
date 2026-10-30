# SP71 — Evidence-driven application completion: prepare → review → handoff → confirm

**Date:** 2026-10-30  
**Baseline (SP70 merged main):** `c7d6682aaa3af83f41ec3cfca779ab23d48a4de4`.  
**Plan subpart:** SP21 P0-B / Agentic SmartPloy user journey §2, application completion and privacy-preserving employer handoff.  
**Production status:** Source/CI only until an independently signed-in OVH release receipt exists.

## Concrete defect

SP69–SP70 gave a clean CV → application mode → vacancy selection → draft path. But the existing Application Studio heading could still show the generic "Your private draft is ready" even when documents were unsaved, an employer attempt was reserved, the ATS connection was unavailable, a browser receipt was only observed, or independent submission had been acknowledged. Users had to inspect several long technical sections to find their next action.

This can be dangerous: **a draft, a browser-observed receipt, a reserved attempt, a user self-report and an independently verified provider receipt are distinct states.**

## Implemented scope

- Reuse the existing authenticated `ApplicationStudio` and all server-owned workspace, partner-readiness, browser-packet, reviewed-rights, one-shot claim, provider-receipt and tracking-agent services. **No new API, database migration, provider credential, polling worker, external package or submission privilege.**
- Add one deterministic, pure `applicationNextStep` presentation reducer with a documented priority:
  1. Durable **provider acknowledged** — sent; do not send again.
  2. **Self-reported applied** — user report; not independently verified.
  3. **Reserved attempt**, with or without browser-observed evidence — no automatic retry; reconcile.
  4. **Browser-observed** receipt — evidence only; not ATS verified.
  5. **Unsaved edits** — save the exact draft through the existing owner-bound revisioned endpoint.
  6. **Attempt status unknown** — fail closed and avoid promising another send.
  7. **Handoff blocked/unknown** — direct to existing preflight blockers.
  8. Explicitly reviewed partner rights + one-use final readiness — link to existing separate human approval; not submitted.
  9. Manual/browser form — private prepared draft; user reviews and handles employer form.
- Replace the generic draft headline with a single context-specific title, status, explanation, and **one next-action control**. A *Save my edits* button reuses the existing `save()`; every other action is a local anchored navigation to existing elements. No new mutation or browser send from status display.
- Preserve the SP70 editor navigation and add an anchor to browser-observed confirmation evidence; all action targets are hardcoded local anchors. Source/private CV text is never interpolated into a URL or forwarded to external AI.

## Required reuse-first / REA record

| Candidate | Status / contribution |
| --- | --- |
| Existing `web/src/ApplicationStudio.tsx` | **REUSED/ADAPTED**: current exact-owner revision handling, server preflight reads, safe employer links, saved CV/letter and outcome control; no new server mutation |
| Existing `web/src/types.ts`, `api.ts` contracts | **REUSED UNCHANGED**: workspaces, browser readiness, durable review, partner/receipt, anti-duplicate policies |
| Existing `web/src/styles.css` | **ADAPTED**: existing navy/blue/slate type and panel system, compact status presentation |
| Existing Vitest + Playwright synthetic API | **ADAPTED**: source+integration tests, one new screenshot and explicit negative safety cases |
| `morluto/rea` and externally discovered comparable UI apps | **REA_NOT_APPLICABLE**: complete authorized first-party TS/React source and existing exact domain-specific API contracts already available, no missing opaque module or program to reconstruct. No REA tool was executed; no third-party code extraction or build-time speedup claimed. Consider REA for separately authorized opaque components only. |
| SP71 new code | **NEW MINIMAL**: pure status-to-next-action reducer, tests, status panel UI and CSS |

**License:** SmartPloy first-party code reused within the same repository. No foreign code copied. **Savings:** unknown, no measured comparison baseline.

## Validation and safety acceptance

- Unit tests cover provider-acknowledged precedence; self-report vs employer verification; reserved attempt with/without browser receipt; unsaved revisions; missing attempt status (fail-closed); missing handoff and server blockers; authorized partner vs manual fallback; no false "sent" status from an AutoApply draft.
- React integration tests verify one next action per draft, editor jump anchors, owner-bound Save edits, no partner send side effect, reserved attempts and missing attempt-status tests, provider-acknowledged case locked from sending.
- Playwright synthetic CV-first upload → chosen job → saved draft must visibly show the new next-action panel. The test never contacts a real employer or uses a real CV.
- Existing cross-account, cross-draft, final partner right, provider duplicate, browser companion, and Postgres tests must keep passing; no test fixture is evidence of real application submission.
- CI acceptance: exact pull-request head, 5/5 checks (web, browser, API/Postgres, fixture production Compose, exact-checkout review). Native ObumDelivery/OVH exact-image SHA and signed-in production acceptance are **separate release gates**.
- No KEHA P67 production activation without KEHA approval and safe source configuration.

## Progress and next blocked gates

**DONE at source scope:** status reducer and in-editor action, reused authenticated owner-bound Save, tests and docs created.  
**IN PROGRESS:** exact-branch CI, review and merge.  
**BLOCKED:** native OVH release credentials and independent proof of production SHA / signed-in acceptance; KEHA production API approval; any automated employer submission without verified specific rights and final applicant approval.
