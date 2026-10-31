# SP87 — CV-first onboarding and application-mode navigation

## Defect reproduced from source (2026-10-31)

The signed-in landing component (`StartChoices`) showed Manual, Assisted and Automatic even when `cv.present=false`. The Apply wizard (`ApplicationJourney`) displayed mode buttons and instructions saying the applicant could choose a method before uploading. A completed-account dashboard placed a decorative hero before the application journey, and saving a first-ever CV from the master editor left the user on the profile page instead of returning to the application method decision.

Those are genuine frontend design errors **independent** of whether source is deployed to OVH. A GitHub green check or production `/healthz` response does not certify the public frontend is up-to-date.

## New connected applicant experience

1. Every signed-in dashboard and first-use landing starts with **Step 1: upload PDF/DOCX or create a CV**. Both actions work without an AI connection, search-setup completion or approval of employer transfer. CV-less users can browse jobs separately but cannot select an application mode.
2. Immediately after a successful CV upload, open the guided Apply page with **Step 2: choose Manual, Assisted or Automatic**. On first creation in the master CV editor, saving a CV navigates to the same Step 2. An existing connected CV enables the choices immediately.
3. A selected mode leads to CV-derived current jobs. Manual opens the original employer site; Assisted creates and reviews actual CV and letter documents, with optional browser companion form assistance; Automatic prepares private matched drafts and then offers the **existing SP86 foreground partner-authorized** three-job submission after exact applicant review.
4. CV replacement/removal invalidates the old selected mode and job. No upload, CV creation, filter or mode selection sends an employer application or implies approved profile facts. Existing CVs remain private.
5. Both first-use and completed-account dashboards place the CV-first application journey at the top, before any marketing hero.

## Security and QA

- Navigation and visible mode cards both fail closed when the CV is absent. The application endpoint still independently requires eligible CV/approved evidence before preparing.
- Applicant identity and CV revision protections, explicit employer approval and prior cross-device attempt locks remain unchanged.
- The job-matching feed may be empty: the UI must explain verified availability rather than invent recommendations.
- Regression tests cover first login with no CV, optional AI outage, stored CV return, CV creator save, locked modes, allowed general browsing and review-first AutoApply expectations.
- Release requires post-merge **exact-main 5/5 CI**, native OVH digest and release-SHA parity, two signed-in applicant tests and a fresh public web/companion check. GitHub isolated Docker CI is not production deployment.

## Reuse vs new

Reused `StartChoices`, `ApplicationJourney`, `App` existing upload and master editor `onSaved`, CV-first retrieval, the prior SP86 Assisted/AutoApply flows and login/CV scope guards. New code changes sequencing, locked states, responsive progress presentation and regression tests. No REA source duplication is appropriate for this first-party UI state fix.

## Post-deploy signed-in acceptance

Account A without CV: first screen must say **Start with your CV.**, show Upload/Create buttons, hide all three application method buttons, permit **Just find jobs** only as browse. Upload CV and verify wizard Step 2 appears without a default selection. Switch Manual→Assisted→Automatic and verify each flow's job actions.

Account B with connected CV: first screen must say **CV connected. Choose how to apply.**, show exactly the three mode actions, and never contact an employer merely by selecting. Create from scratch on an empty account must navigate to Step 2 after save; replacing or deleting the CV clears any previous job/mode selection. Verify provider receipts separately in a pre-authorized pilot.
