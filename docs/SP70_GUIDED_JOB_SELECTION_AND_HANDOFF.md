# SP70 — One deliberate current-job choice → one clear next action

Date: **2026-10-30**. P0 continuity after SP69. Baseline main: `9174648ec03a88657adbce35e6d78d7c45da41c2`.
This is a UI and test increment of SP21/P0-B and Agentic SmartPloy §2; it does not introduce automatic employer submission.

## User problem and expected end-to-end experience

SP69 separated the CV and application-method choice, but each matched job still exposed several simultaneous actions. It was possible to open a new private draft without any visual *chosen job* step. The progress indicator did not distinguish **matching** from **selecting** a vacancy. Application Studio then displayed a long document and submission form without clickable step navigation. There was also potential to misrepresent the current mode of the *page* as a durable method/status of an older application draft.

### SP70 experience

1. **CV connected:** real owner-scoped CV and current database matching remain unchanged.
2. **Manual / Assisted / Automatic** must be explicitly chosen; no employer permission inferred.
3. **Manual or Assisted:** each current job has **Choose this job**. Clicking highlights exactly one current vacancy and reveals the method-specific action *inside the chosen card*. No draft is created by the choice. Until a job is chosen, only a read-only posting link is exposed, never a Save or Prepare action.
   - Manual: original **Apply on employer site** link, plus optional **Save application draft**. User sends the employer form.
   - Assisted/filter-only: original employer site; no AI document creation.
   - Assisted/documents or supported form assistance: **Prepare CV & application** opens existing exact-job private Application Studio. AI text is review-only. Employer sending is still separate.
   - Deep link from main Find Jobs: API-pinned, source-current exact job is already visibly selected (but never prepared without user click). If source, filter or account changes so the job is not in the displayed live set, the next-action buttons disappear.
4. **Automatic:** independently choose up to 15 current jobs via existing checkboxes; **Prepare applications & start agents** creates exact-job private drafts and case agents. No employer contact or submission, no implied ATS permission. The existing stop/retry/success/blocked results remain. Mode buttons are locked during an in-flight batch; leaving AutoApply clears its stale selection.
5. **Draft editor:** a click-ready navigation row jumps to CV, letter, employer form options (for editable drafts), and outcome controls. Headers and status reflect actual workspace/provider evidence rather than a stale page-level Manual/Assisted/Automatic selection. The existing independently reviewed partner/browser gates, one-use attempts and genuine provider acknowledgments remain unchanged.
6. **Progress:** step 3 stays active until a real current job is selected; step 4 becomes active after a deliberate selection. This progress is a *guidance hint*, not a server receipt or application status.

## Mandatory existing-code reuse record

| Part | Existing system examined | SP70 treatment |
| --- | --- | --- |
| CV import and user identity | `uploadCV`, `getCVJobMatches`, `getSession`, account-bound frontend | **Reuse unchanged**; no data copy to external services |
| Job selection | `ApplicationJourney`, `SearchJobCard`, Search-selected canonical key | **Adapt** existing card; single-job choice is local UI state |
| Draft editor | `startApplicationWorkspace`, `ApplicationStudio`, saved exact-job workspace IDs | **Reuse unchanged engine**, add section anchors and status copy |
| Automatic batch | `onPrepareSelectedJobs`, existing per-case tracking, stop/retry and browser evidence | **Reuse unchanged backend**, harden mode transitions in UI |
| Employer submission | existing Lever/Ashby authorization and one-use review, manual browser companion | **Reuse and preserve restrictions**; no added send capability |
| Styles & tests | existing site CSS, Vitest, Playwright synthetic fixtures, API/Postgres CI | **Adapt**; no new npm dependency, service or database migration |

**New from scratch:** chosen-job UI-only state and current-job gate, explicit mode-specific action panel, selected/progress messages, editor section link row, keyboard/focus CSS and tests. **No new application engine, credentials, external provider integration, schema, API or worker.**

**REA audit:** Existing authorized React/TypeScript and backend code is complete and directly inspectable; no missing or opaque module has been identified for reverse engineering. REA was reviewed in SP69 and **was not executed for SP70**, so do not claim generated/reconstructed code or estimated savings. The mandatory reuse-first objective was met using audited first-party components directly. Future REA use requires an authorized target and a reproducible evidence receipt before adapted code is accepted.

## Security invariants and acceptance

- Choosing a method/job **never** creates a case or sends CV data externally. Only an explicit Save/Prepare/authorized submit action can start the appropriate workflow.
- Unsigned/foreign-account match responses are never published. New selection state resets on CV replacement, source-selected job change, or account switch.
- Search changes can hide the previously chosen job; absent/retired jobs do not expose a draft-creation button.
- Switching out of AutoApply removes prior batch selections, rather than silently reusing them on return. A pending batch cannot be silently redirected by the mode chooser; stop is honored between jobs.
- Explicitly separate *draft prepared*, *attempt reserved*, *browser observed*, *self-reported applied*, and *provider acknowledged*.
- Tests: manual choice before Save, assisted filter-only separation, deep-linked selected job, paginated jobs, hidden stale selection, mode switch, no duplicate batch, no cross-owner write, browser first-use and manual flow, editor navigation to real sections and disabled partner final submit on unapproved jobs.
- No production release claim without merge SHA + exact-head 5/5 CI + native ObumDelivery/OVH image acceptance + signed-in browser proof. No KEHA production source activation while approval is pending.

## Status ledger

| Plan | Change | State |
| --- | --- | --- |
| SP21 P0-A / SP70-1 | One exact job selection, progress, relevant primary next action | Source code implemented on feature branch; CI pending |
| SP21 P0-B / SP70-2 | In-editor clickable stage navigation, truthful status | Source code implemented; CI pending |
| SP70-3 | Existing safety invariants and synthetic browser/unit tests | Tests added; CI pending |
| SP69 issue #232 | Exact production rollout and owner acceptance | Independent release gate, not established |
| KEHA P67 | Official source credentials / API approval | Separate pending dependency; no changes |

Verification receipts will be recorded against PR run SHA, not inferred from source commits.
