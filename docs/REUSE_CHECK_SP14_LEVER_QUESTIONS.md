# SP14 — Lever supplemental question review: reuse and safety decision

**Baseline:** [SmartPloy SP13 review head \`a30716b167c662195b30d25f65e57acdea48056b\`](https://github.com/galapoto/smartploy/commit/a30716b167c662195b30d25f65e57acdea48056b) from [DRAFT #151](https://github.com/galapoto/smartploy/pull/151), which itself depends on the unmerged integrated [DRAFT #149](https://github.com/galapoto/smartploy/pull/149). **Status:** owner requested continuation; SOURCE REVIEW AND SYNTHETIC TESTS ONLY, not merged, externally deployed or permitted to submit automatically.

## What was inspected BEFORE implementation

| Exact source | Verified capability and gap | Decision |
| --- | --- | --- |
| SmartPloy \`browser-companion/logic.mjs\` blob \`747bb13201e525f6f96b5c3cb8ca36e8235cc6c6\`, \`popup.mjs\` blob \`dfd60902484442bb4855e9cac797c13f2f20c378\` on SP13 | Already has owner/15-minute/job-bound v2 packet, contact+cover letter mapping, visible native setter, final consent and one-shot attempt. Unknown questions are skipped. | EXTEND EXISTING COMPANION. Do not build another extension, browser service, profile DB, uploader or submit engine. |
| SmartPloy \`browser_handoff.py\` blob \`df744c723dc5b253ac5e2af91127c089f3f1a67c\` on SP13 | Approved factual contact and CV identity, no open-ended answer authority | Do NOT add model-guessed questions or new backend answer-store in SP14. |
| ObumAI [form_mapper.py](https://github.com/obumai/obumellm/blob/a324fc0f330aeffe869dea7f96243156bc6af669/obumellm/application/form_mapper.py) blob \`d279d84aeee21d87a2291698628c1220e1f793f2\` | Deterministic mapping and unsafe-purpose rejection. \`safety_for_purpose\` is a *plan*, not a live executor. | Reuse its reviewed-field vs blocked/unknown *policy*; do not import ObumAI Python into the extension. |
| ObumAI \`questionnaire.py\`, existing ObumAI evidence rules | Prepares grounded Q/A drafts; no verified live ATS answer submission | Future typed, versioned answer-memory service after consent/provenance and tenant isolation; NOT silently auto-applied. |
| [Safe Application Prefill](https://github.com/HimavanthMahesh/safe-application-prefill/blob/1619963fa24506e91a3b0ce75067f82632e71b3d/core.js) blob \`9efd62384ebf921a95263a78704c5add9440e47a\`; [LICENSE](https://github.com/HimavanthMahesh/safe-application-prefill/blob/1619963fa24506e91a3b0ce75067f82632e71b3d/LICENSE) MIT | Browser field risk classes: legal/protected/eligibility unknown => do not autofill; extension avoids submit/file/CAPTCHA; some source selectors are too broad for legal/safe auto-transfer. | Adapt *behavioral requirements*, independently write bounded English/Finnish/Swedish filters. Do not copy extension/other code wholesale. |
| [Yaima](https://github.com/Yaima/agent-apply/blob/e5061bc0455ea61b75b59edbe73296ab5bbe03ca/agent/forms/apply.py), MIT | Human-reviewed final submit and manual exception handling | Retain SmartPloy's original final-submit approval, not Yaima's browser runner. |
| [neonwatty job-apply-policy](https://github.com/neonwatty/job-apply-plugin/blob/370204c58b1137d08c5a7e7449538ae6447be0b9/scripts/job_apply_policy.py), MIT | Inert answer/campaign consent and revision tracking | Later approved answer memory only; current ephemeral applicant-typed answers do not warrant a second state store. |
| [ApplyAI](https://github.com/muhammad-saadd/applyai/blob/d4a97b5643aa219592883a43b068fc18dff94678/utils/ai.js), MIT | ATS selectors but raw CV/answer information sent to \`api.openai.com\` | REJECT external-answer generator or importing broad host-permission extension. |

No code from unlicensed/AGPL/GPL/Commons-Clause sources is imported or modified. The new supplemental classifier and browser action are first-party adaptations from independently inspected requirements, not vendored upstream files. No bundled fonts, telemetry, networking, external package or remote LLM.

## Narrow required behavior

1. Only handle **two** recognized low-risk plain-text question classes on the **same approved Lever form**: (a) where the applicant heard about the job, and (b) interest in the role. A real person types each answer in the ephemeral extension popup. No inference from candidate profile, cover-letter rewrite or cloud model.
2. The current form must have a **visible, empty, enabled, non-readonly** \`input[type=text]\` or \`textarea\`, a unique non-ambiguous recognized label and no forbidden legal/demographic/visa/sponsorship/salary terms in its descriptors. \`select\`, \`checkbox\`, \`radio\`, uploads, passwords, hidden or arbitrary questions are NOT filled.
3. Bind selected field index + id + name + type + original visible label + same exact Lever URL. Revalidate them on the employer page **at fill time**; reject a changed form/SPA rerender, duplicate labels, missing/ambiguous fields, suspicious descriptor, unsupported input, oversize/control-character answer, or a filled field. Never overwrite.
4. Use existing packet, account/session, explicit applicant button click, active-tab match, existing PDF and final-submission approval. The supplemental step has **no final-submit capability**, no background processing and no browser storage. If skipped or unknown required questions remain, the existing final preflight must still block sending.
5. Browser-page setter uses only native DOM input/change events, no \`innerHTML\`, \`eval\`, text interpreted as instructions, fetch/XHR/credential access, cross-origin browsing, CAPTCHA/MFA, or automatic retry.
6. Clearly label source-local insertion as **not an employer saved answer/accepted application**.

## Negative test requirements

- Wrong job, wrong HTTPS host, changed tab/URL, changed label/DOM, changed type/name/id, disabled/hidden or already filled field -> BLOCK without acting.
- Visa, work authorization, sponsorship, EEO/gender/race/religion, salary, birth/age, criminal/legal attestations, privacy agreement, security challenge, files, checkboxes and unknown required questions -> manual review only.
- Duplicate matching questions, overlong answer, invalid Unicode/control characters, more than permitted text-field count -> stop/skip.
- No automatic model inference, original employer form submit, upload or stored private applicant answer.
- Local isolated fixtures + adversarial synthetic Chromium + exact source test; **actual** submitted application or employer-confirmed receipt is NOT tested here.

## Release position

**Implementation is strictly a SP14 review candidate layered on SP13.** No safe live employer application may be claimed until downstream source/consent rights, actual signed-in applicant choice, ObumDelivery qualified CI, account isolation and real employer confirmation are accepted. Current \`main\`/OVH unchanged.

**Estimated incremental effort:** one narrow helper + existing popup integration + synthetic fixtures, approximately 1–3 engineer-days to first review in an environment with available CI, plus unknown time for review and legitimate external acceptance. This is a provisional estimate, not an elapsed-time promise or measured reuse saving.
