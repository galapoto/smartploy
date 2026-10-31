# SP86: Assisted handoff and approved provider AutoApply batch

## What ships in source

- **Assisted:** the job-specific Application Studio now shows a short review → save → verified packet → exact employer site walkthrough. It reuses the existing version-locked browser companion that can fill ordinary approved contact fields and attach the exact CV PDF for hosted Lever, Ashby and Greenhouse forms; unresolved employer questions and legal consents stay with the applicant. No autofill is counted as submission.
- **AutoApply:** once the applicant separately reviews each job's CV, letter, form and record (the existing owner-scoped 10-minute review intent), up to **three** exact Lever/Ashby employer jobs with independently reviewed, employer-specific API permission can be selected, previewed and submitted in one foreground gesture. The form lists each job/employer and requires two explicit checkboxes and a final confirmation.
- The new batch endpoint `POST /api/v1/autoapply/submit-reviewed-batch` checks the signed-in applicant's OIDC identity, CSRF/same-origin headers, private ownership, current job, revision, document/approved-contact digests, fresh review intent, live rights, duplicate job identity and provider readiness for **all** jobs before attempting any provider I/O.
- For each eligible exact job, it calls the original `_submit_to_authorized_partner` without bypassing the atomic PostgreSQL one-shot employer claim or approved Ashby form preflight. It stores true provider-issued application IDs and moves the workspace to `provider_acknowledged`. A 429, timeout or uncertain outcome **halts** the remaining batch. No automatic retries.
- The client revalidates all selected employer/source hashes before sending and rechecks the OIDC subject after each private API read/POST; a login switch or unsaved edits block sending. No password scraping, CAPTCHA-solving, unreviewed jobs or generalized LinkedIn/Workday submissions.

## Important boundaries

- This is a **foreground, applicant-approved AutoApply batch** for employer partners; it is not a background bot or a promise that every public job board is authorized for automation.
- Employer integration credentials and independent rights attestation must already exist. Applicant checkboxes, job postings and CV matches are never substituted for these.
- Without a partner integration, jobs remain in Assisted/Manual; the user can fill the employer's form using the companion and submit personally.
- A genuinely unattended worker requires a separately approved legal/consent, expiration/revocation, job-specific review and employer contract design; SP86 does not activate it.
- GitHub CI and synthetic partner mocks do not prove the revised release is running on OVH or that a **real** employer received a submission. The native rollout and real consenting partner pilot remain under production gate SP84 (#250).

## Reuse vs new

**Reused:** all signed-in review-intent and ownership gates, one-shot employer attempt/reconciliation, employer permissions, Lever/Ashby provider transports and PostgreSQL receipts, CV/PDF renderer, application agents, browser companion and existing UI states.

**New:** bounded exact-job batch orchestration, frontend consented selection, Assisted walkthrough, focused API/React/Postgres tests, release documentation. No REA code was adopted because the existing first-party one-shot sender is more specific, safer and already tested.

## Acceptance evidence

See PR CI: `test` (Python/PostgreSQL), `web` (TypeScript and Vitest), `browser` (Chromium) and `deploy-stack` (isolated production Docker Compose fixture), followed by the exact-checkout receipt. A real deployment has a **separate** release SHA/backup/rollback and two-account acceptance requirement.
