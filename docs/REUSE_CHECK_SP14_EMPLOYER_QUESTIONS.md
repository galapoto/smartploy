# SP14 — Reuse check: employer-specific reviewed question answers

**Date:** 2026-10-18. **Review status:** source-only draft; no employer submissions or deploy.
**Starting point:** SmartPloy PDF/Lever companion PR #151 at a30716b167c662195b30d25f65e57acdea48056b.
**Plan:** [Reuse-first master plan PR #150](https://github.com/galapoto/smartploy/pull/150).

## Existing implementations checked before writing

| Existing source | Confirmed function | Decision |
|---|---|---|
| SmartPloy first-party browser companion and handoff v2 at a30716b | Reviewed and expiring packet, employer/job scoped browser fill, upload, one-attempt submit, receipts | Extend without replacing |
| [ObumAI questionnaire](https://github.com/obumai/obumellm/blob/main/obumellm/application/questionnaire.py) | Evidence-backed motivation/fit/availability drafts, unknown questions need user review | Reuse as draft source in future; never treat unreviewed suggestions as facts |
| [ObumAI form mapper](https://github.com/obumai/obumellm/blob/main/obumellm/application/form_mapper.py) | Purpose classification and default-deny unknown, legal, upload and submit controls | Follow its human-only boundary; no second general HTML parser |
| [Yaima/agent-apply](https://github.com/Yaima/agent-apply/blob/e5061bc0455ea61b75b59edbe73296ab5bbe03ca/agent/forms/apply.py) | MIT. Human review for unknown fields, safe browser reinspection | Do not import a second Playwright runtime |
| [career-ops](https://github.com/career-ops-hq/career-ops/blob/9e4326b35a8ee716081b9169f44e83d232a99289/docs/APPLY_AUTOFILL.md) | MIT. ATS quirks, employer-form liveness and final human submit | Reuse conservative design without wholesale import |
| [neonwatty job-apply policy](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job_apply_policy.py) | MIT. Sensitive-answer revisions, claim/bounded-authority concepts | Candidate for future approved answer vault, not imported now |

**License/provenance:** Only first-party SmartPloy code added. MIT sources were reviewed for capabilities; their source files were not vendored. No AGPL/GPL/Commons-Clause/unlicensed project copied or rewritten to evade its licensing.

## Product behavior delivered in this draft

- Inspect only required, empty, visible, editable, uniquely labeled unknown text or textarea fields on the **same HTTPS Lever /apply job**. A maximum of 12 questions and 1,500 characters per answer; respect each field's maxlength.
- Keep salary/compensation, visa/work authorization, citizenship, EEO, protected data, legal/privacy consent, medical/criminal/background checks and related Finnish/Swedish phrases **manual**. Never auto-fill checkbox/radio/select/file/password controls.
- Applicant types or pastes a truthful answer in an ephemeral local popup; ObumAI questionnaire drafts may be pasted only after personal verification. No model call, hidden inference, background bot or answer persistence.
- Require separate confirmation before sending any answer to the employer form. Warn that employer JavaScript may transmit immediately when input/change fires.
- Revalidate current user-reviewed packet, exact job/tab URL, form label, type, id, name, placeholder, maxlength, required/empty/visible state and current DOM index before each action.
- Reactive DOM changes cause fail-closed or partial/manual-review outcomes; no automatic retry or final-submit action.
- Existing SP13 exact PDF digest, explicit user attachment and one-click reservation remain unchanged.

## Testing and rollout gates

New pure Node tests, 5 synthetic Chromium scenarios and Python security-contract tests run through existing GitHub CI and proposed ObumDelivery pipeline. Synthetic tests do not contact employers and do not prove that a real form accepted an answer.

**Remaining:** account-scoped approved-answer bank; SmartPloy/ObumAI draft-answer API with explicit per-job approval; guarded select/conditional controls; crash-safe multi-worker authorization and queue; permitted other ATS; employer receipt verification; trusted deployment and real applicant acceptance. These must reuse existing ObumAI capabilities rather than creating a second answer generator.
## SP14 safety fix — no duplicate click after editing a CV

Review of the existing native companion found the initial client-side one-attempt key
included the CV revision/digest and could therefore change between document edits.
The revised key is stable for the same tenant-scoped workspace + HTTPS Lever job ID,
and a Web Locks exclusive claim serializes simultaneous extension popups before
checking existing opaque storage, rechecking final preflight, reserving, and clicking.
It uses the standard browser Web Locks API rather than importing a second
dependency. Absence of the API is a **stop**, never an unlocked fallback.
**Scope:** one Chrome profile only. Different browsers/devices and manual user
submissions still require the future server-side atomic application claim.
See test_browser_attempt_lock_contract.py and the Node concurrency tests.
