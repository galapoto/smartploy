# SP21 — Urgent CV-first application journey plan

**Priority: P0 product-blocker. Updated: 2026-10-22.**
**Owner objective:** Make a first-time applicant complete a coherent sequence:
**Choose how to apply → Upload CV once → Match current jobs in SmartPloy's database → Pick a job → Prepare/apply → Next job.**
No obscure technical settings or dead-end buttons.

## User-accepted product spec and exact workflow

The main navigation and first-use start must show clear distinct entry paths:

| Path | What the applicant chooses | What SmartPloy does | What still requires the applicant |
| --- | --- | --- | --- |
| **Find Jobs** | Search/filter only | Show all current database postings, independent of CV | Optional choose Manual / Assisted from any job |
| **Manual Application** | CV then target job | Parse locally, show CV-derived matches, prepare an owner-bound application workspace, open original employer link and keep a draft | Complete and submit employer form; report result when known |
| **Assisted Application** | Matching only, CV tailoring, or form help | CV-derived matches, selection, local first-party CV/letter editor and permitted reviewed browser form fill | Review facts, answer sensitive questions, final submission where no authorized transport |
| **AutoApply** | Explicit job selections or approved user limits | CV-derived matches, durable per-job draft/workspace, background drafts where explicitly opted in | Real employer final send ONLY on authorized provider with one-time server claim and trustworthy ACK; all unsupported forms go to Needs Review |

**Shared sub-steps:** mode → CV upload → ranked current jobs → choose one → build/edit draft → authorized external action or Needs Review → next. A job in Search can be moved to Manual/Assisted; no CV needed to merely browse.
**CV & Documents:** a separate clear page with Upload, Replace, Review extracted text, Download, and job-specific Tailor/Letter through the *selected* application's editor. A CV upload is **not** approved evidence or submission permission.
**Saved progress:** existing per-user CV and application workspace/drafts, not browser-local PII. Mode selection may be ephemeral during first MVP; application state remains server durable.

## Milestones

### P0-A — SP21: Make a real usable first journey immediately
- Preserve backend OIDC binding, source worker, Postgres jobs and CV parser.
- Add owner-only, read-only **CV-to-current-database match endpoint**. Parse stored CV text locally; derive search *signals* (not asserted credentials); reuse `SearchPreferences`, `search_jobs`, bilingual job-title matching and source-current gate. If no signals, return unranked current jobs with explicit uncertainty instead of fabricate a fit. Do not send CV or matching results to ObumAI/employers.
- New first-use choice and simplified page with Manual / Assisted / Auto; job search remains separate. Progress: **1 choose → 2 upload → 3 choose job → 4 application draft/review**. Mode not equal to employer submit consent.
- Refactor upload success to navigate directly to ranked jobs and meaningful next action, not silently to Profile; preserve approved facts.
- Per-job **Apply manually / Prepare with AI** both call the existing owner-bound `startApplicationWorkspace` and open the existing Application Studio; do not invent a silent submit or a queue that doesn't exist.
- Explicit notice for blocked or unsupported final automatic employer submission and a next step. Clear loading, error, empty-job and no-CV states.
- Tests: CV ranking from actual uploaded text and current database; only owner can read; unrelated driving matches not shown as recommendations; upload-to-matches path; mode selection & job selection; no automatic employer POST.
- Release: exact-head 5/5 GitHub CI, main merge, then guarded OVH exact SHA; independent signed-in first-user acceptance.

### P0-B — Immediate next: Single application screen
- Consolidate CV facts approval and job-specific document controls into one guided editor: CV → Letter → Questions → Review → submit/handoff, with **Next application** and **Needs review**.
- Fix misleading CV Editor / Cover Letter buttons that currently route to Find Jobs; either open actual selected application editor or ask to pick a job.
- Make queued attempts user-owned, stored in existing application workspaces, with explicit statuses: Not started / Draft / Needs review / Employer-acknowledged / Self-reported.

### P0-C — Real end-to-end browser submission
- The existing MV3 companion fills limited reviewed Lever fields and attaches a reviewed PDF. **It currently forbids its own automatic final click.** Separate narrowly approved Lever partner API path needs actual posting-rights registry, credential, one-shot applicant approval and provider ACK.
- Build **server-issued, short-lived, one-use browser claim/redemption** tied to verified user, exact job URL, CV/letter hash, employer rights, reviewed questions, and reserved cross-device attempt ID.
- Build runner per *permitted employer form* (not generic CAPTCHA bypass): stable form detection, schema mapping, approved fields, exact PDF upload, browser login challenges requiring user, final click only with claim, verify acknowledgment, save receipt, never ambiguous auto-retry.
- Installable extension / hosted managed browser worker, permission boundaries, recovery and observability, timeouts, idempotency, per-user opt in, audited QA with consenting test employer. This is not completed by SP21.
- For CAPTCHA/MFA, hidden or sensitive questions, unavailable provider permission, dynamic unsupported pages or uncertain results, **save draft and request human action**. Never call job applied absent reliable external acknowledgment.

### P1 — ObumAI contribution and measurement
- OVH SP20 log: 4 installed local Ollama models, local bridge PASS, broader `ObumAI integration: disabled`. Existing app operates its own source matching, local CV parse, workspaces, worker and drafts.
- Integrate documented ObumAI agent interfaces only with explicit per-job privacy/AI consent, reviewed source terms and cost/latency budget. AI is a *proposal* layer for letters/question answers, never authorization or ownership.
- Add per-stage local metrics: CV uploaded → extracted → matches seen → selected → documents ready → manually applied / authorized provider ACK → exception. Separately count local model invocations/errors and **remote ObumAI durable jobs**. Do not fabricate ObumAI contribution from bridge connectivity.

## Reuse vs scratch — SP21
**Reused**: existing `cv_import.parse_cv`, `cv_storage` owner-scoped stored CV, `search_preferences.search_jobs` bilingual/role relevance, source-current job repository, `startApplicationWorkspace`, `ApplicationStudio`, protected `runPrivateMutation`, ZITADEL identity, current React navigation and tests.
**New**: deterministic CV signal extraction and safe read-only matching endpoint, mode-centric CV-first journey UI, concise application-mode routing and regression tests. No external library, new crawler, employer action, credential, account store or new table.

## Evidence and deployment truth
Baseline deployed and verified by operator log: SP20 `2bc677e3d5b9b9e0cfdfd6fd0295a0fda86ce2b0` (healthy API/worker/web/Postgres, local Ollama bridge PASS, full ObumAI integration disabled).
This document is implementation plan, NOT proof of a merged feature or OVH rollout. Each run must report file changes, source reuse, scratch changes, verified CI SHA and production SHA separately. No generic browser final-send claims until a real employer ACK is verified.
