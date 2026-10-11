# SmartPloy Nordic workspace, brand and CV Studio (v1)

This release implements the owner-approved simple Nordic identity, rather
than the prior letter-S placeholder. Design reference: bright Scandinavian
dashboard, navy/cyan accents, readable sidebar and restrained Helsinki motif.

## Included

- The actual approved Nordic SmartPloy mark is included as
  `web/public/smartploy-mark.png` and as the browser favicon
  `web/public/favicon.png`. A separate vector ObumAI orbital motif marks
  the existing product-navigation link (not an authentication shortcut).
- Responsive dashboard and workspace navigation: dashboard, find jobs, application
  tracker, CV/profile, career tools, career insights, source activity and settings.
- All job cards/statistics use **actual API records**; never create sample jobs,
  fabricate fit scores, source freshness, imports or submission confirmations.
- Private CV upload (text-based PDF or DOCX, max 5 MB), preview, download,
  replacement and deletion. Parser runs locally and never calls ObumAI.
- `smartploy_cv_files` stores one original private CV per authenticated profile
  with content digest and text-only extraction. The user may remove it.
- Manual profile facts: add, explicitly approve/revoke, delete. Only approved
  facts affect scoring and candidate evidence forwarded to authorized services.
- Add a job manually using the existing trusted manual-ingest boundary.
  This is NOT a live job source poll.
- Source status, ObumAI readiness and preparations remain truthful and
  clearly unavailable where integration is not configured.

## Deliberately not included

- LinkedIn account scraping or account import.
- Fetching Finnish jobs from unapproved sources. Job Market Finland, Kuntarekry
  and public ATS sources remain disabled until each integration meets its
  source/terms/secret acceptance criteria.
- Automatic CV claim approval. Uploaded CV content is not itself evidence
  until reviewed.
- Final job submission, email sending, or external application actions.
- OIDC cutover. Cloudflare Access remains the trusted identity gate until
  verified Obum Identity commissioning.
- Automatic AI-written completed documents: current CV Tailor/Cover Letter
  controls explain required ObumAI setup rather than generating placeholder text.
  Full artifact/download functionality is still tracked in #55 / #65.

## Security gates and deployment

- Filename, magic bytes, length, zip expansion and PDF page count are bounded.
- File content is parsed as text only; no user-supplied HTML/JS is rendered.
- CV and facts are stored/read/deleted by the resolved authenticated
  profile_id, never by caller-supplied profile identifiers.
- No CV content leaves the server during upload unless the authenticated user
  explicitly downloads it. Uploads are not forwarded to ObumAI.
- Private file responses use attachment disposition, nosniff and no-store.
- PostgreSQL migration `010_private_cv_upload.sql` must run **before**
  new API/Web images are served. The guarded deploy script already handles
  backup, migration, exact running image verification and health gates.

After PR CI approval and merge, operator on `obum-core-01` should review the
code and deploy via the existing guarded deployment path. Test live auth, CV
upload and per-user data isolation before declaring the CV workflow generally
available.

The full suite must pass Python/PostgreSQL tests, web build/test, and
Docker production backup/restore release checks.
