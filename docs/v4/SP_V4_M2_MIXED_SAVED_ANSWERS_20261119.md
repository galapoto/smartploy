# SmartPloy V4 — reuse saved answers when a real form has NEW questions

**Date:** 19 November 2026. **Authority:** V4 production-first §§1.1, 4–7 and 12; `SP-V4-ONE-PROFILE-APPLY-001` steps 1, 4–7. **Baseline:** first-party `galapoto/smartploy@89bdbe76347edf89bb8c2bf73fc93b16aea39f56`, merged main after companion 0.6.2. This is an AutoApply behavior correction, not a new executor.

## The observed source defect

`browser-companion/popup.mjs::onStartAutoApply` previously stopped on the **first** NEW, changed or protected employer question, even if the same inspected form contained ordinary questions with **exact, already approved, saved profile answers**. Those known answers stayed blank and the owner had to repeat earlier work. This was apparent from the control flow; it does not establish a live employer reproduction.

## Implementation and correctness

- Reuse `onReviewQuestions` and `suggestSavedAnswers` to label exact saved answers versus NEW/changed questions. The review result now includes the existing `memory.reused` count; nothing new is inferred from a CV.
- If a mixed form includes at least one approved saved answer, use the **existing** `onFillQuestions` after the ordinary explicit fill consent; blank unknown fields are skipped by `validateReviewedAnswers`. Never derive a text answer from an old, differently worded label.
- **After** the bounded fill, invoke `onReviewQuestions` exactly once again. A React/ATS handler might expose new questions or clear a previously filled answer. Do not automatically replay a failed or uncertain fill.
- Always stop at applicant handoff on the mixed-question path, even if the reinspection reports no remaining ordinary questions. Sensitive/consent/legal requirements remain manual, and no employer submit permission, claim or attempt is consumed.
- If no saved answer exists, continue existing no-write handoff. If consent is declined, writing fails, reinspection fails, or the employer changes the form, stop without any final action.

## Copied → sanitized → adopted

| Classification | Original project / version / source | Destination / changes |
| --- | --- | --- |
| COPIED | **none** | No unchanged third-party or first-party source copied into a new file |
| REUSED | https://github.com/galapoto/smartploy @ `89bdbe76347edf89bb8c2bf73fc93b16aea39f56`; `browser-companion/questions.mjs::suggestSavedAnswers,validateReviewedAnswers`, `popup.mjs::onReviewQuestions,onFillQuestions`, `page-questions.mjs::fillReviewedAnswers` | All existing safe answer planning, explicit consent, exact DOM validation, and no-submit controls remain in place |
| ADAPTED / INTEGRATED | Same first-party `browser-companion/popup.mjs::onStartAutoApply,onReviewQuestions` | One conditional path for saved answers on mixed forms and a single fresh reinspection after a positive fill |
| SANITIZED | Existing exact-job, signed-in review, sensitive question, no-retry and short-lived packet boundaries | No external answers, credentials, new permissions, network paths, files, dependencies or bypasses introduced |
| NEW | `browser-companion/tests/start-autoapply.test.mjs`; `browser-companion/tests/questions.test.mjs` | Targeted negative and positive regression assertions; this evidence document and the associated component receipt |

**REA decision:** `REA_NOT_APPLICABLE`. Source is readable, owned, exact-version first-party code, and its current deterministic acceptance tests are available. Running opaque software reconstruction provides no legitimate implementation evidence or safety benefit. No third-party code imported; code-reuse percentage and engineering time savings: **NOT_MEASURED**.

## Verification / release status

- Expected command: `node --test browser-companion/tests/start-autoapply.test.mjs browser-companion/tests/questions.test.mjs`; native full browser companion, Python, Playwright/Chromium, web and deploy gates must qualify the exact PR head.
- Regression objectives: known saved field fills despite a second new field; changed label cannot reuse an old answer; sensitive questions stay human-only; cancelled/uncertain known-answer fill stops; no final claim even after successful reinspection.
- At documentation authoring: **SOURCE COMMITTED on feature branch**, exact-head CI **NOT VERIFIED**, production deployment **NOT VERIFIED**, actual signed-in employer form and employer receipt **NOT VERIFIED**. Update actual evidence only after checking results.
- Production promotion continues to require exact merged-main SHA, backup-first OIDC deploy, public package and release evidence, signed-in application UI and owner-authorized employer review. Branch merge is not a live release.
