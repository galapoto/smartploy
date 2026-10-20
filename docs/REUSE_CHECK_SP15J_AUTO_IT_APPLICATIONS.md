# SP15j — Source-fed, user-opted automatic IT match → private applications

## User outcome / exact previous gap

SmartPloy already polls public employer ATS feeds (Lever, Greenhouse,
SmartRecruiters), Job Market Finland and permitted Kuntarekry feeds and
ranks personal matches in Finnish/English. But the ONLY working route
from a match to an editable CV/letter workspace was a manual
`POST /api/v1/jobs/{key}/application-workspace` / "Prepare documents"
on **each individual job**. The user explicitly needs SmartPloy to
fetch IT jobs and apply without providing any URLs.

**SP15j makes existing job fetching -> matching -> automatic LOCAL
application preparation a single continuous product path**. The actual
provider application remains a separate action governed by SP15e/i:
there are no universal employer credentials, and no unsupported
site can honestly be marked applied.

## REUSE EVIDENCE — inspected original blobs before new code

| Prebuilt and REUSED (not copied from unlicensed external repos) | Original blob | Current use |
| --- | --- | --- |
| `smartploy/sources/public_ats.py` (Lever, Greenhouse, SmartRecruiters read-only GET adapters) | existing SP15i source | Existing periodic source poll, no second crawler |
| `smartploy/worker_schedule.py`, `smartploy/worker_runtime.py` | `e5353d1e`, `8e2abf5d` | Existing worker task/lease/backoff, new local task |
| `smartploy/search_preferences.py` | `dd5a1ab3` | Existing Finnish/English title aliases, location, languages, seniority, verified-match uncertainty; **no second ranking engine** |
| `smartploy/search_preference_storage.py` and migration 013 | `61c50a5c` | Already revisioned private per-user search settings JSON; adds opt-in field there rather than a second table |
| `smartploy/application_workspace.py` | existing SP15h | Existing `new_workspace` uses uploaded CV or ONLY owner-approved facts and noninvented cover-letter skeleton |
| `smartploy/application_workspace_storage.py` and migrations 011/023 | `804e736a` | Original per-profile PostgreSQL and memory `create_or_get`, remains owner scoped and idempotent |
| `smartploy/identity.py` | `4be837dd` | Already verified active user+profile identity join; no email-only tenancy |
| `smartploy/cv_storage.py` | `fa1e9b43` | Private uploaded CV; never sent to ObumAI or an employer by this task |
| `smartploy/employer_submit_claim_storage.py` | existing SP15a | Original sticky claim guard blocks new drafts after a prior Lever application attempt |
| Existing `web/src/SearchSetup.tsx`, `web/src/App.tsx`, `web/src/api.ts` | existing SP15i | Settings/role wizard, no new UI shell/account stack |
| Original `deploy/personal/docker-compose.yml` | `8f413c49` | Reuses 4-container operator stack; one worker opt-in flag, no extra service |

This run borrowed **no externally licensed source** and created no
second CV generator, browser automation engine, model backend, posting
scraper, recruiter tracking CRM or SaaS subscription. The external
Job Board API read paths are read-only; submission APIs require
employer-authorized keys per the provider documentation.

## Genuinely NEW missing functionality

- `smartploy/auto_application_queue.py` **one small source module**:
  reuse original `search_jobs` recommended lane, require >=65%
  *preference alignment* (NOT qualification evidence), no explicit
  mismatched role/location/language, current posting, credible HTTPS
  application URL, reject known senior/lead unless user explicitly
  wants senior roles. Up to 5 new, owner-private, locally generated
  application drafts/day. Preserve existing status/receipts, no AI
  dispatch, browser click, employer network call, or bogus submission
  count. A shared PostgreSQL advisory transaction lock serializes
  worker replicas and concurrent users for the quota, **without
  introducing another DB table**.
- Original search preference model/storage and React search settings
  **adapted** with explicit `auto_drafts_enabled: boolean`, default
  FALSE, unambiguous owner-only per-profile opt-in and a one-click
  editable IT/data/QA preset. Switching to General mode disarms the
  opt-in. The worker discovers only active, independently verified
  owners with enabled personalized search settings.
- Original scheduled worker **adapted** to register one
  `application:auto-draft-matches` task when the operator enables
  `SMARTPLOY_WORKER_LOCAL_AUTO_DRAFT_ENABLED=true`. The worker
  consumes jobs the original source tasks already fetched. It
  builds profiles/CVs only from their owning account, checks a fresh
  consent/revision after per-profile lock, never calls ObumAI or ATS,
  and emits only aggregated metrics (not CV text, names or URLs).
  Default operator switch stays FALSE.
- Original signed-in FastAPI gets a narrow
  `POST /api/v1/application-workspaces/prepare-matches`:
  explicit one-click owner confirmation, matching *saved* criteria
  revision, verified session/CSRF, existing cross-device sticky
  claim checks, bounded batch. No user can supply another
  person's profile ID, unseen job key, fabricated qualifications
  or submit authority. Works even if scheduled auto-prep remains
  disabled, because the owner initiates the safe local operation.
- React search wizard can choose one-click editable IT roles and
  opt into recurring local drafts. "My applications" and "Find jobs"
  both offer **Find and prepare matched IT applications** with a
  factual result (new drafts, none submitted), linking to the
  actual existing Application Studio/editor.
- NEW targeted unit/FastAPI/PostgreSQL/React tests prove
  idempotency, posted vs closed, seniority, unknown vs mismatched
  qualification, tenant isolation, ignored non-opted-in identities,
  exact preference revocation, no network/AI/employer actions,
  daily quota, anti-duplicate existing claim, general search opt-out,
  and no injected CV facts. Existing broader regression suite runs too.

## Systemic limits / release gate

This advances **the AUTO DISCOVER + MATCH + DRAFT part** of requested
end-to-end IT auto-apply. It does **not** automatically send employer
applications in the background. Existing SP15f–h signed-in, explicitly
confirmed and employer-authorized standard Lever API can submit one
applicant-approved posting, get actual applicationId, store non-editable
provider acknowledgment. Other employers still require form-by-form
rightful assisted/manual submission. SP15i OIDC production activation
and native ObumDelivery #32 are still unaccepted, main/OVH have not
received this feature and the public SmartPloy site still presents
Cloudflare Access login. The worker local feature defaults OFF.
No CV/profile is fabricated from personal chat memories; verified
SmartPloy account facts and uploaded CV are the source of truth.

**Never count created drafts as submitted applications or report a fake
provider ID.** Real success next: operator-approved immutable #168/#169
release, authorized ZITADEL live login and source worker at the website,
opted-in real user with approved CV/IT criteria, actual 5 locally created
drafts from real current IT postings with a human review and separate
verified employer submission + receipt. 
