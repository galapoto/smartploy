# SmartPloy Application Studio — first usable release

## Actual workflow

SmartPloy is no longer blocked from *preparing* a job application by the
unfinished ObumAI machine-auth configuration.

1. The owner signs into the existing, Access-protected SmartPloy app.
2. Upload a PDF/DOCX CV under **CV & profile**, or manually enter and
   explicitly approve career facts (name/contact can now be approved too).
3. In **Find jobs**, choose **Prepare documents** on any current vacancy.
   Preparation is allowed even when a job's evidence match is too low for
   automatic AI drafting; the user deliberately selects that job.
4. SmartPloy opens a private application workspace. The initial CV draft
   reproduces the user's uploaded extracted CV text *verbatim*, or includes
   only approved profile facts. The starter letter names the actual job and
   employer but uses conspicuous prompts for any unverified personal claims.
5. Edit and save both documents. Save requires the expected revision to
   prevent silent overwrites from other tabs.
6. Download editable DOCX or selectable-text PDF for both documents.
7. Open the original employer URL in another tab and complete the employer's
   application form manually.
8. After completing it yourself, optionally record **self-reported applied**.
   This is never treated as independently verified submission. The existing
   application CRM's `actually_submitted` metric is not modified.

## API and persistence

- `POST /api/v1/jobs/{canonical_key}/application-workspace` — create/idempotent
  open; fails closed for missing/closed job and insufficient CV/approved facts.
- `GET /api/v1/application-workspaces` — list owner-bound drafts.
- `GET /api/v1/application-workspaces/{workspace_id}` — get owner-bound draft.
- `PUT /api/v1/application-workspaces/{workspace_id}` — edit both documents
  with strict max sizes and an optimistic revision.
- `GET /api/v1/application-workspaces/{workspace_id}/download/cv/{pdf|docx}`
- `GET /api/v1/application-workspaces/{workspace_id}/download/letter/{pdf|docx}`
- `POST /api/v1/application-workspaces/{workspace_id}/report-applied` —
  requires a user confirmation and remains **self-reported**, not verified.
- `DELETE /api/v1/application-workspaces/{workspace_id}` — owner deletes own
  stored draft (does not remove the separately uploaded source CV).

Migration 011 creates `smartploy_application_workspaces`. All reads and
mutations resolve `profile_id` from the authenticated Access/OIDC principal,
not from caller-supplied identifiers. No new public inbound ports.
PDFs/DOCX are generated in memory on demand from saved, owner-reviewed text;
no external AI call, browser automation or remote file fetch is performed.
Exports use a safe attachment name, controlled MIME, nosniff and no-store.

## Security/truth boundaries

- The CV upload is personal information: never log it, echo it in error
  messages, forward it to ObumAI without authorization, or commit it to Git.
- No unknown AI-generated claims are added to the CV.
- Cover letter prompts must be reviewed and replaced by the applicant.
- Uploaded CV text may be longer than the 30,000-character editor limit;
  the API rejects rather than silently truncating it.
- Downloads are saved content at the last successful revision. The UI disables
  export links while there are unsaved edits.
- Employer-site URLs are displayed as explicit links, not fetched by SmartPloy.
- User-reported applied status does not authorize final submission or fake an
  employer acknowledgment.
- `external_actions_authorized=false` remains unchanged.
- The existing ObumAI durable-job integration is preserved; no attempt to
  bypass scoped machine identity or source forwarding permissions is made.
- v2 evidence-bound ObumAI artifact rendering (#55 / draft PR #65) remains
  a separate future capability, not a prerequisite for manual application work.

## Production rollout

After CI is green and the PR merged, the host operator reviews the exact SHA
and follows the existing guarded release deployment:

```bash
cd /srv/obum/stacks/smartploy
SHA=REVIEWED_40_CHARACTER_SHA
sudo git fetch origin main
sudo git checkout --detach "$SHA"
sudo bash deploy/personal/scripts/preflight.sh
sudo bash deploy/personal/scripts/deploy.sh "$SHA"
sudo bash deploy/personal/scripts/assert-healthy-stack.sh
sudo bash deploy/personal/scripts/assert-running-images.sh "$SHA"
sudo bash deploy/personal/scripts/live-acceptance.sh
sudo bash deploy/personal/scripts/release-evidence.sh --online
```

The migration and PostgreSQL backup are handled by `deploy.sh`. The release
may briefly restart SmartPloy API/web/worker, not the separate ObumAI stack.

Authenticated browser acceptance must test: CV upload, owner-specific
workspace opening for a real job, editable save and DOCX/PDF download,
an explicit self-reported status, and deletion. Production go-live issue #57
stays open until those checks are recorded.

## Remaining steps toward fully automated applications

1. Commission an approved scoped ObumAI machine identity and service
   connectivity, with owner-approved CV forwarding and source-terms checks.
2. Generate fully evidence-bound v2 tailored CV/letter content (PR #65/#55)
   and review edit support. Add immutable artifact hashes and audit.
3. Implement source-specific browser/form connectors with terms, MFA,
   explicit per-job approval, screenshot/confirmation evidence, deduplication,
   audit and a separate kill switch. **No external submission is enabled
   by this release.**
