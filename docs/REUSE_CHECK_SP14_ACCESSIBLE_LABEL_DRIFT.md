# Reuse check: SP14 live accessible question labels

**Base:** SmartPloy integrated draft eedc89aef3d4b5e4569d121f09a293ea39be30d9; no production promotion.
**Feature:** prevent reviewed ordinary-text answers from being placed when employer form semantics drift in additional labels.

## What existed before this change
- `browser-companion/questions.mjs` and `page-questions.mjs`: first-party screened question planning and actual-page validation.
- Review PR #155: sensitive identifiers, duplicate ordinary labels, post-event detach/index checks.
- Existing `web/browser-tests/lever-questions.e2e.ts`: isolated synthetic Chromium, no employer navigation or submission.
- ObumAI form mapper/questionnaire is an upstream reasoning/draft capability, not a live DOM/browser execution or authenticated field naming oracle.

## Gap and decision
A live input may retain its first `<label>` and unchanged id/name while gaining a new sensitive associated label, `aria-label`, `aria-labelledby` target or title. The old validator read only the first label/expected identifiers; a misleading or changed ARIA name could be missed.

**Reuse:** extend the existing first-party `fillReviewedAnswers` executor, retain its existing sensitive regex and restricted identifier rules, and reuse the existing browser test harness. No new runtime, dependencies, browser permissions, model calls, external source files, licenses or network requests.

The patch checks all associated native labels, accessible naming references and title both **before** filling and **after** the browser input/change events. Dangling ARIA labels or >8 associated labels/references stop; all unknown/legally significant questions remain manual. This is conservative by design and may reduce automated coverage where a form has ambiguous labels.

## Verification, boundaries, release
- Run the existing exact-head Node/React/Python, isolated Chromium, and Compose review gates.
- New synthetic cases cover secondary sensitive labels, ARIA names/references, dangling references and post-input label mutation. They never submit real applications.
- Do not claim this validates the employer site as a whole, prevents employer JavaScript from receiving data after a user-approved fill, or proves live acceptance.
- **Still HOLD:** live acceptance, exact-owner release approval, provider terms/security review and server-side cross-browser atomic attempt claims.
