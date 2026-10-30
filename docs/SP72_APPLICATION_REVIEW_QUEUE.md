# SP72 — My Applications review queue after Manual, Assisted and AutoApply preparation

**Date:** 2026-10-30  
**Baseline:** SP71 merged main `55e271dbfb9b2bb0ef59f6fe51ad97da097f0666`  
**Plan:** SP21 candidate flow P0-B, Agentic SmartPloy Gate 2 candidate-only action inbox, follow-on to SP69/70/71.

## What problem is fixed

After an AutoApply batch, users can have many **private saved drafts**, yet the application editor previously offered a flat list and a single bottom-of-page Next draft control. Users could not see the difference between (1) drafts still needing review, (2) cases they reported submitting, and (3) cases actually acknowledged by an employer without scanning every row.

SP72 adds an **owner-scoped review queue** above the existing Application Studio editor. The queue includes category counts and the next relevant review action without introducing a new API, database, permission or employer send.

## Actual behavior

- Three honest categories and an **All** filter: **Drafts to finish**, **Self-reported**, **Employer acknowledged**. A self-report is never counted as independently employer acknowledged.
- Counts come **only from the authenticated owner-scoped workspace rows currently loaded** by the existing `getApplicationWorkspaces()`, possibly plus an older owner-scoped workspace opened through the existing verified `getApplicationWorkspaceById()`. The UI explicitly labels these as loaded counts rather than all applications in the account; newer/older pagination is not invented.
- Filters change only which existing job buttons appear in the **left list**. They do not mutate any application or send any contact, CV, letter or browser packet.
- **Review next draft** reuses the existing `nextDraft` selector and `pick()` with the original unsaved-edit confirmation. If only the currently open draft remains, **Continue this draft** is a real anchor to its CV editor. Zero drafts means no fake/inert review control.
- A selected case outside the current filter stays open and is labeled as such, rather than silently switching jobs. Existing server-confirmed per-case next-action guidance (SP71) remains the authority for employer attempts and partner permissions; no per-list item is guessed to be "ready to submit."
- The original Agent Zero inbox stays active. There are no new background tasks or notifications.

## Reuse-first proof

| Source component | Treatment |
| --- | --- |
| `web/src/ApplicationStudio.tsx` | **REUSED/ADAPTED**: original exact account verification, bounded private workspace list, selected older-case GET, local `pick()`, dirty confirmation and next-draft selector |
| `web/src/applicationNextStep.ts` and original partner/attempt APIs | **REUSED UNCHANGED**: only verified provider acknowledgments signal independently submitted; no new final-action path |
| `web/src/ApplicationAgentInbox.tsx` | **REUSED UNCHANGED**: existing in-app reminders and owner boundary |
| `web/src/styles.css` | **ADAPTED**: existing site palette/spacing; responsive full-width queue and keyboard-accessible filter buttons |
| `web/src/ApplicationStudio.test.tsx`, `web/browser-tests/onboarding.e2e.ts` | **ADAPTED**: owner-bound tests and built-site synthetic CV → exact job → private draft acceptance |
| `web/src/applicationReviewQueue.ts`, `.test.ts` | **NEW MINIMAL**: pure categorization of already-loaded workspaces with no requests or side effects |

**REA decision: `REA_NOT_APPLICABLE`.** The complete, authorized first-party source already implements safe owner-bound workspace reads, attempt handling, agents, filters and tests. No unavailable opaque executable/component was identified whose behavior requires reconstruction. REA was **not executed** on competitor code, and no measured build-time savings or reconstructed code is claimed. No external code or dependency was imported. Speedup is **unknown**.

## Safety and acceptance

1. Existing same-email different-user/account switch, stale request, delayed private read, dirty editor, agent and employer-rights protections must keep passing.
2. Counts and filters never equate self-report or browser-observed receipt with a trusted employer acknowledgment; draft status alone does not imply it can be submitted automatically.
3. The original `pick()` unsaved-edit confirmation blocks accidental loss while moving to a different draft.
4. The filter is local UI state tied to the account-keyed `ApplicationStudio` mount; no CV text, auth token, employer packet or user details are sent by queue interactions.
5. Source unit tests cover counts, filtering, empty state, loaded older case, no fake verified submission; React tests cover cross-category selection, unsaved change guard, no side effects; Playwright verifies the actual rendered review queue after a synthetic CV upload, job choice and draft creation.
6. Exact-head GitHub CI 5/5 required for source integration; native Woodpecker/ObumDelivery and **actual signed-in OVH** remain separate release gates. No production deployment claimed from synthetic tests.

## Delivery status

- **Done at source**: full-width Review queue, status filters, per-category loaded counts, next draft CTA, deterministic helper and tests.
- **In progress**: exact-head CI, independent review and merge into `main`.
- **Blocked**: native ObumDelivery publisher authorization, actual OVH deployment/rollback receipt and authenticated connected-CV end-to-end acceptance, tracked in [SmartPloy issue #232](https://github.com/galapoto/smartploy/issues/232).
- **Independent external gate**: KEHA P67 production approval; employer-specific partner automation rights and exact final applicant review. No rights expanded here.
