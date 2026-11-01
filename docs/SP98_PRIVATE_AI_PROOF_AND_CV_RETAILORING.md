# SP98 — Real private model generation proof and non-destructive CV re-tailoring

## Why

SP97 is live at \`1f07dbdfff4c4daf8a8c3df65d9b50e1dd6c4ea7\`. Its
\`/api/v1/local-ai/status\` reads Ollama's installed-model catalog; that is
**not a successful inference proof**. Previously, adding another AI CV summary
was simply refused, even if the prior summary had a recognizable editor format.
Users need trustworthy, clearly differentiated tools.

## Working functionality

1. **Check AI connection** remains a read-only installed-model status request.
2. A new **Run real AI test** button in the saved application's writing studio
   requests **one actual generation** from Ollama using a fixed synthetic prompt
   \`READY\`. No CV, approved career facts, employer, job listing or cover-letter
   data enters the prompt or response. Inference proof is only shown after
   Ollama completes and returns the expected synthetic word. The result is
   deliberately not logged or stored. A failed or timed-out inference reports
   a safe error, rather than a misleading successful model-status icon.
3. The test requires explicit user confirmation, exact authenticated stable
   account ID, matching same-origin browser controls and a strict true payload.
   The service uses a 90-second per-account in-memory cooldown and an 8-KiB
   maximum result body. No auto retry, polling or background inference. If
   SmartPloy runs more API workers, use a durable shared limiter.
4. Private suggestions still require separately consented and revision-checked
   \`/ai-suggestions\`; the probe does **not** consent to that workflow.
5. Applicant-specific AI CV summaries are now previewed as a complete CV
   comparison **before** explicit insertion. The editor can replace only the
   exact recognized single-paragraph header from a prior SmartPloy AI action;
   ambiguous/relocated headings cannot be automatically replaced. The original
   text below the header is kept byte-for-byte. Older CVs without a generated
   header get one inserted above unchanged text. Existing one-step undo works
   before save; manual edits remain the applicant's choice. AI cover letter can
   always be used independently if a CV replacement is blocked.

## Reuse vs new

- **Reuse:** private Ollama-only bridge, owner-bound session identity and
  profile repositories, deliberate applicant confirmation, review-only JSON
  suggestion contract, job/CV studio, browser-only document comparisons,
  previous in-memory exact-revision undo, guarded OIDC release.
- **New:** one isolated synthetic probe function, one same-origin POST route
  with per-owner cooldown, one typed frontend action/receipt, pure CV preview
  helper, and frontend/backend/Chromium regression coverage.
- REA_NOT_APPLICABLE: no third-party repo reuse needed; existing first-party
  audited contracts give a shorter and safer path.

## Test gates / nonclaims

- Unit: no personal input in test prompt; fixed bounded inference request;
  reject oversized, malformed, interrupted and provider-error replies;
  no public credentials; negative anonymous/consent tests; owner/origin
  authorization and rate-limit test.
- Browser: status vs actual generation distinction, account-change safety,
  reversible CV proposal; isolated Chromium Assisted CV-first acceptance
  with synthetic mocked response (no Ollama, no employer network).
- CI: require all five jobs PASS for PR head and merged-main SHA before
  authorized OVH operator release.
- Deployment: exact approved SHA \`deploy.sh\` followed by online release
  evidence, independent public frontend/API revision parity. No user data in
  release reports.
- Signed-in live acceptance: select job, press Check AI connection, press
  Run real AI test with explicit approval, observe proof of genuine inference,
  separately request private tailored wording from approved profile facts,
  compare CV and letter, choose/undo/save/reopen/export.
- The self-test does **not** prove a job-specific draft is accurate or make
  AutoApply an employer submission. Manual/Assisted/Auto modes retain their
  existing independent employer-rights checks.
