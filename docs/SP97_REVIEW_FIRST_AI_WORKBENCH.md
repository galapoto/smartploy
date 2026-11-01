# SP97 — Review-first private AI writing workbench

## Outcome and scope

Production base: SP96 exact merged SHA `62b73599d46ffceccc52b941a1dc7cf3ae20b638` (operator successfully deployed; release and public API revision parity verified). SP97 is a **new candidate**; do not claim its changes are publicly live until a new exact release receipt exists.

### Lane A — AI is visible and correctly explained

- **Career tools → AI writing assistant** opens the existing CV-first Assisted journey, or the exact already selected saved application editor; it never starts an application or uses the model on navigation.
- The card works even for an empty account by routing to the CV upload gate first.
- Distinguish SmartPloy's `/api/v1/local-ai/status` Ollama availability from `health.obumai_configured`, which is the separate ObumAI gateway. Do not mistakenly declare local evidence-backed letter generation unavailable because the gateway is absent.
- Existing complete English/Finnish approved-evidence letters remain available when model inference is disabled.

### Lane B — sophisticated applicant document review

- Existing full Finnish/English evidence letter proposals now open a **side-by-side original/proposed text review**; generating a letter never immediately overwrites personal draft wording.
- Applicant explicitly clicks **Use proposed Finnish/English letter** or **Keep my current letter**. Missing-information and review-note fields stay separate from letter prose.
- Existing private Ollama proposal now provides its full cover-letter comparison, generated CV wording, risks and review notes, with individual CV-only / letter-only / both controls.
- Approved AI insertion and evidence template acceptance remain unsaved draft edits. **Undo last generated edit** restores only the immediately prior content, only in the exact signed-in workspace/revision, before saving. Any manual keystroke revokes that undo, avoiding silent destruction of later edits.
- A per-editor change epoch ensures asynchronous account verification cannot commit an old suggestion over newly typed text.
- Never stack a second AI-marked CV-summary block on top of an existing AI summary with uncertain boundaries. Surface a manual-edit instruction instead; no guessed deletion of applicant content.

### Existing safety and reuse

- No new backend dependency, unapproved profile-fact transfer, employer contact, browser token or send authorization.
- Reuses private `proposeEvidenceLetter`, explicit consented `requestLocalAISuggestions`, approved evidence records, existing one-use employer claims and exact owner/revision verification.
- Proposal compares on the browser only, without saving or contacting a provider. Current partner-ATS and manual application flows are unchanged.
- New code: one read-only comparison component/CSS; workspace-scoped proposal and undo UI; honest AI entry/status text; test expansions. REA_NOT_APPLICABLE (reuse of existing checked-in verified source is safer than a third-party replacement).
- Do not count deterministic document-quality checks as LLM output; do not infer Ollama enabled from bridge network health.

## Acceptance gates

1. 5/5 CI lanes green on exact PR-head and merged-main SHA (TypeScript/Vitest, browser isolation, backend/PostgreSQL, Compose smoke, exact checkout receipt).
2. OVH operator guarded exact-SHA deploy and `release-evidence.sh --online`.
3. Independent HTTPS `/release.json` and `/healthz` revision parity.
4. Signed-in applicant UAT: CV → select Assisted → choose real current job → create drafts → AI tools reachable → compare private evidence template letter without losing current edits → reject/accept → undo → save → reopen/download; separately check local model connection and consented suggestion preview.
5. No actual employer/provider submission unless separately documented employer rights, applicant approval and provider-issued acknowledgment.

## Status

SP97 branch source prepared for pull-request CI. **Not yet deployed.**
