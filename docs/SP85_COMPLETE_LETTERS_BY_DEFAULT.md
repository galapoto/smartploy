# SP85 — complete cover letters by default

## Problem fixed
New application workspaces previously started with review-guide placeholders such as `[Explain in your own words...]`, although the explicit language action already generated real Finnish/English letter prose. Applicants could download a coaching template instead of a cover letter.

## Changes
- Reuse `smartploy.complete_letter.compose_completed_letter` as the **default** content for `new_workspace`. The explicit language change keeps the same already-tested composer.
- Reuse the existing exact, published job-language classifier: Finnish only when the listing explicitly indicates Finnish; ambiguous or mixed language remains English. Never infer applicant fluency from the job listing or their CV.
- Keep applicant qualifications constrained to approved job-matched facts. If the evidence/name is missing, the composer produces incomplete **prose**, not invented credentials or embedded editing commands. The explicit language proposal still returns `complete` and `missing_information` separately.
- Existing database workspaces, applicant-edited text, revision numbers and employer-review state are not automatically rewritten. The visible language buttons can replace older drafts only by applicant action and confirmation.
- UI explicitly explains incomplete evidence, old drafts, manual editing, save/review and no employer contact.
- No new network calls, AI requirements, employer forms, employer claims, source ingestion or migrations.

## Reuse-first
Uses the existing matching/scoring, approved evidence, CV/application workspace and PDF/DOCX renderers; no REA/external code warranted. Existing legacy helper is retained for compatibility but not used when opening new workspaces.

## Acceptance
- New English and Finnish workspaces have complete textual introductions, evidence paragraphs when justified, and real closings.
- No `[Explain...]` or `[Kerro...]` coaching text enters newly generated letters or PDF/DOCX.
- Unapproved/unmatched facts do not become applicant claims.
- Unknown or mixed advertised language doesn't force Finnish.
- Saving and final employer transmission retain existing explicit consent, owner/revision checks, one-shot safety ledgers and authorization boundaries.

## Release boundary
GitHub CI is source/fixture evidence only. No OVH deploy or real employer post is implied. New default applies to newly created workspaces after release, not pre-existing drafts.
