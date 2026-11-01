# SP101 — CV replacement transition gate

**Plan / stage:** BEFORE: CV replacement disabled only the upload trigger, while application-mode choices and preparation controls could remain usable against the previous CV. AFTER: both entry screens pause these operations immediately; AutoApply batch callbacks observe an invalidated scope and stop remaining jobs after any already-started request.

**Baseline:** `804747bd9f01f999f9e806dcf96459bb215bb8f1` (`main`, 2026-11-01). Feature branch: `feature/sp101-cv-update-transition-gate-20261101`.

## Existing code reviewed and reused

- `web/src/StartChoices.tsx`: original accessible CV-first journey, no second state machine.
- `web/src/App.tsx`: existing `busyCV`, CV replacement, account identity check, method reset and signed-in navigation.
- `web/src/ApplicationJourney.tsx`: existing `queueScope`, bounded AutoApply, stop-request callback, first-party review and employer guards.
- Existing React Testing Library/Vitest fixtures and GitHub CI; no new external dependency.

**REA_FIRST_001:** REA_NOT_APPLICABLE. Scope was an authorized first-party React state transition, not opaque third-party executable, website or recorded API. No external source copied. REA revision/tool not used. `savings=unknown`.

## Changes

1. The entry page announces upload state and temporarily disables Manual, Assisted, Automatic, CV editor and saved drafts navigation until the upload completes.
2. The connected CV filename is visible (escaped React text), so users can verify the CV in use before choosing a method.
3. The Apply page blocks stale mode/job choices, draft and batch preparation during CV replacement, and clears the old shortlist and focused job.
4. An AutoApply loop in flight receives a changed scope and stop request immediately when `uploading` becomes true; already-started server operations are **not** falsely claimed to be cancelled or rolled back.
5. Existing employer authorization, applicant final review, identity and CSRF boundaries remain unchanged.

## Validation and rollout

Added focused tests for paused choices, restored mode activation, cleared old job focus and an in-flight batch stop callback. CI / Web build and backend source gates must pass at the exact PR SHA. Production sign-in, 2-account isolation, browser keyboard/mobile/zoom checks and exact-SHA deployment evidence remain separate required gates.

**Status:** proposed for review; not deployed; no employer application sent.
