# Application documents v2 (implementation lane)

This branch introduces v2 evidence validation behind `SMARTPLOY_APPLICATION_CONTRACT_V2=true`.
The committed production configuration remains v1, and v1 queued jobs are still parsed with the
v1 schema. Never enable v2 production rollout until render/persistence/download acceptance is complete.

## Shape

- Immutable v2 package contract: `smartploy.application.package.v2`
- New model output schema: `smartploy.application.draft.v2`
- Structured CV: headline, evidence-linked professional summary, header, skills, experience,
  education, certifications, projects, languages, and do-not-claim list.
- Evidence-linked cover letter paragraphs.
- Separate risks/review checklist.
- Identity/contact header fields require a matching approved fact, exactly as recorded,
  including matching fact category; a matching email string alone never confers trust.
- Invalid or unparseable v2 completion becomes `completed_unparsed`, not submitted.
- v1 packages retain their original ID, result validator and ObumAI instructions.

## Mandatory remaining gates before v2 production

1. Implement immutable PostgreSQL artifact storage (migration 007) with hash, size and owner isolation.
2. Render four ATS-safe downloadable files using validated structured v2 content only.
3. Require binary round-trip, PDF/DOCX text inspection, bounded size and reproducible checks.
4. Implement authenticated list/download APIs (nosniff, safe names, no filesystem path input).
5. Display download links and clear draft/not-submitted status in SmartPloy web UI.
6. Pass tests for tenant isolation, source-forwarding restrictions and v1 compatibility.
7. Review generated text claims for evidence accuracy; a referenced fact ID is necessary but
   does not by itself prove that the authored sentence is semantically true.

## Authentication and authority

No Cloudflare Access policy was removed. No production authentication values changed. SmartPloy
has no upload, send, or final job-application submission authority in this lane.

Ref: #55.
