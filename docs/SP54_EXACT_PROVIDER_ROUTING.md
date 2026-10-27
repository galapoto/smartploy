# SP54 — Exact provider routing and honest manual fallback in Application Studio

**Date:** 27 October 2026 (Europe/Helsinki)  
**Plan subpart:** SP21 P0 CV-first application journey; SP43 hosted Greenhouse reviewed assistance; SP47 manual observed receipts; SP52/53 authorized Lever/Ashby one-shot partner submissions.  
**Baseline:** SP53 main `1c527ceba88094548d748e325911cbe8252ff335`.  
**Scope:** signed-in first-party frontend correctness and negative tests, **not** deployment or employer authorization.

## Defect before this change

`partnerKind(application_url)` returned `"lever"` for **every** URL that was not hosted at `jobs.ashbyhq.com` (including `boards.greenhouse.io`, unknown employer domains, malformed URLs, HTTP and lookalike domains). As a result, the app requested Lever partner-readiness/receipts for jobs that were never Lever jobs and displayed the wrong `Official Lever partner submission` UI. A provider-specific response could also be shown without enforcing that it matched the current job's provider. The backend generally rejected a wrong job, but the UI suggested capability and evidence that were not there. This is a core user-journey defect, not a request for a new ATS integration.

## Reused source and original SP54 changes

- **Reused unchanged:** original owner-bound `ApplicationStudio` workspace and browser-assist flow; `getLeverPartnerReadiness`/`getLeverPartnerReceipt` and Ashby equivalents; original signed-in employer review, one-use claim, provider send and receipt persistence; original `safeExternalJobUrl` employer-site link and manual `I applied on employer site` reporting.
- **New glue:** strict UI-only recognition of HTTPS `jobs.lever.co`, `jobs.eu.lever.co` and `jobs.ashbyhq.com`; no userinfo, nondefault port or lookalike domains. No other site is assigned a partner action.
- **Core journey:** unsupported provider jobs do **not** call any Lever/Ashby direct partner API; they show a clear manual application path while retaining the same reviewed browser companion and employer-site link.
- **Privacy/correctness:** provider-readiness and receipts must match the current provider before display. Direct-review and final-send handlers reject mismatched providers even if stale UI state remains. An applicant workspace whose employer URL changes at the same revision invalidates prior private editor/packet results.
- **Receipt honesty:** unknown hostnames never inherit a Lever identity or receipt label. Already acknowledged status remains a provider status, not guessed employer branding.
- **No new adapter:** no new ATS submission code, browser engine, secrets, database table, credential, runtime dependency or third-party source. This is adaptation of existing first-party code, with no claimed measured time saving.

## Executable regression expectations

`web/src/ApplicationStudio.test.tsx` reuses the original mocked OIDC/workspace/handoff/receipt frontend test harness. It asserts:
1. Supported Lever, EU Lever and Ashby routes remain intact and never cross-call the other provider.
2. Hosted Greenhouse, unrelated domains, lookalike Lever/Ashby domains, plain HTTP, URLs with embedded userinfo and nondefault ports show manual fallback; **zero** direct partner readiness, receipt or submit requests.
3. An unexpected Ashby readiness response for a Lever job does not unlock a partner-send control.
4. An acknowledged workspace with unsupported URL does not display a fabricated Lever receipt label.
5. Existing reviewed CV, manual reporting, authentic owner-bound receipt, application batch and browser tests continue to pass.

## Required real acceptance gates (not provided by this source change)

- Exact PR-head **and independently merged-main** Python/PostgreSQL, frontend, Chromium, Docker and exact-receipt CI must pass.
- Native ObumDelivery `galapoto/smartploy` admission and pinned positive/negative pipeline on the real controller/isolated runner are still unverified. Platform source inventory remains `enabled:false` until operator accepts it.
- The trusted operator must separately perform a backup-first OVH deployment of an approved exact main SHA, attest running image/worker/Chrome companion revision, and test two signed-in distinct accounts.
- Real application delivery requires documented employer rights, fresh individual applicant consent and an actual independently returned provider application ID. Unsupported sites remain manual.

**No real employer request, unattended submission, OVH release, or native self-hosted CI is claimed by SP54.**
