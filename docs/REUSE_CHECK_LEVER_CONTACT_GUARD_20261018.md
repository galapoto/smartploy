# REUSE-CHECK: existing Lever contact mapper hardening (2026-10-18)

Status: review-only; no deployed or employer action. Baseline: [SmartPloy combined draft #153](https://github.com/galapoto/smartploy/pull/153) commit eedc89aef3d4b5e4569d121f09a293ea39be30d9.

## Inspected exact existing code BEFORE patch

| Reusable original | Proven capability / pinned blob | Reuse decision |
| --- | --- | --- |
| SmartPloy browser-companion/logic.mjs | 747bb13201e525f6f96b5c3cb8ca36e8235cc6c6; contact field classifier/plan | AUGMENT first-party mapper, no competing engine |
| SmartPloy browser-companion/popup.mjs | 5e09a5b72efbc8ed8dd3aa107353fadb37756f7b; user-approved native value setter | AUGMENT first-party live checks, preserve source/consent |
| SmartPloy browser-companion/questions.mjs | b8873417f83c32bf03fcbf563814b2c00aec2794; sensitive question classification | REUSE negative-category policy |
| SmartPloy browser-companion/page-questions.mjs | 01965017eb1fb5f20ef3b4b4310a703bc9935e96; duplicate label and post-React event check | REUSE live validation pattern |
| ObumAI [form_mapper.py](https://github.com/obumai/obumellm/blob/a324fc0f330aeffe869dea7f96243156bc6af669/obumellm/application/form_mapper.py) | deterministic purpose/unsafe controls; not a live employer executor | Reference policy, no second browser runtime |
| [Safe Application Prefill](https://github.com/HimavanthMahesh/safe-application-prefill/blob/1619963fa24506e91a3b0ce75067f82632e71b3d/core.js) | MIT top-level license, conservative manual handling for protected field types | Behavioral comparison, NO code copied |

## Actual safety gap

The original contact mapper may treat autocomplete=email or name as trusted BEFORE checking contradictory metadata, allowing a protected field with a misleading label/name to be proposed for user-approved fill. The live filler checked field index, ID, name and type, but NOT current visible label, new duplicate labels or protected field identifiers. React input events could also detach the old field or add required fields after a successful setter.

## Narrow fix, no feature rewrite

- Reject protected, salary, visa, sponsorship, legal/privacy, nationality and sensitive metadata on the planning side BEFORE autocomplete matching, including camelCase/concatenated identifiers.
- In the same existing browser executor, recheck original label/id/name/type, exact active job, visible editable unique target and sensitive metadata at transfer time.
- After native input/change, verify live DOM remains attached and consistent; fail with an explicit manual-review blocker on change. Never auto-resubmit or invent employer confirmation.
- Keep the existing short-lived reviewed packet, separate PDF consent, applicant final-click authorization, Web Locks one-shot reservation, receipt uncertainty, site permissions and all original application work.
- Added three node policy regressions and six synthetic Chromium scenarios, including true/false allowed contacts, altered labels, disguised attributes, duplicate label, React detach and new required field.
- No external code, new dependencies, remote LLM, new extension permission, source-provider traffic or private CV material is imported/sent.

## Review and hold

The candidate must pass exact-head source CI and independent privacy/security review. GitHub Actions PASS is NOT ObumDelivery, OVH or real employer acceptance. Existing ObumDelivery live activation and approved real employer receipt are separately blocked.

Decision: first-party REUSE and bounded safety augmentation; do not rebuild contact field mapper, browser, profile/answer store or full automation product. Planning avoidance roughly 1-2 engineer-days, not a measured speedup. No production authorization from this document.
