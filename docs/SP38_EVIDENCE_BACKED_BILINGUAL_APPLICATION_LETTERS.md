# SP38 — Job-relevant, approved-evidence Finnish/English cover letters

**Plan:** SP21 P0-B single CV-first application editor; Agentic SmartPloy
Gate 1 honest application packages; local AI optional rather than a blocker.
**Baseline:** SP37 `main@5c67b7196d3795921ad6bf1141998a18cfffee12`.
**Date:** 25 October 2026.

## Concrete core gap

Until SP38, the original `new_workspace` generated an English
intro letter using the **first three approved skills/experiences/
education facts**, regardless of whether the employer actually asked
for them. Every letter included an unfilled personal motivation
placeholder, but could foreground unrelated qualifications instead
of relevant evidence. Finnish jobs and `suunnittelija` applicants
were also initially served English copy even when the ATS published
an explicit Finnish language requirement. The existing private
Ollama/ObumAI draft suggestion was optional, off by default, and
could not be considered a substitute for a reliable basic document.

## Source reuse — before new code

1. Reuse the original `smartploy/scoring.py:score_candidate` that
   already computes `matched_evidence_ids` from real job requirements,
   descriptions and the approved `CandidateProfile`. This prevents
   a second, less-tested keyword matching algorithm.
2. Reuse the original `CandidateProfile.approved_facts` and profile
   evidence IDs. Never use unapproved facts, private raw CV sections,
   inferred years, fabricated credentials or guessed language level.
   Show **exact original approved fact values** under their accurate
   type labels (Skill, Experience, Education, Project, etc.) without
   augmenting them with invented assertions. Facts over 260 characters
   are omitted from a short letter, **not truncated**, since that can
   remove a negation/date and reverse the meaning.
3. Reuse the original `new_workspace` in BOTH the explicit
   applicant-selected flow and the consent-controlled
   `prepare_profile_shortlist` job-to-private-draft worker.
   The uploaded CV is still reproduced verbatim, not silently
   rewritten by the new letter generator.
4. Reuse Application Studio's existing versioned
   `PostgresWorkspaceRepository` and `runPrivateAction` account
   and selection gate for post-creation user-selected language.
   The new preview uses the same current source/job fingerprint
   test as the existing local-model suggestion route; the original
   independent employer final-action rights are not changed.

## User-facing behavior

**Initial private application draft:**
- Exact Finnish marker in structured job language
  (`Finnish`, `Suomi`, `fi`, `fi-FI`) → Finnish applicant-review
  text and Finnish type labels.
- Explicit English, unspecified or ambiguous/mixed language →
  English review text, to avoid falsely inferring application language.
- Match up to three job-relevant, **approved** facts via the existing
  scorer. If no approved fact matches, insert an honest explicit
  prompt requesting a truthful example; do not substitute irrelevant
  qualifications.
- In either language, leave a clearly marked personal motivation
  and real example placeholder. The draft is not employer-ready until
  reviewed; one applicant's name is included only if approved.
- Output is short, uses real line breaks, and stays compatible with
  the ORIGINAL PDF/DOCX export path and document-revision ledger.

**Existing draft, explicit choice:**
- The authenticated applicant clicks **Finnish draft** or
  **English draft** beside the existing cover letter editor.
- A new signed-in first-party
  `POST /api/v1/application-workspaces/{workspace_id}/letter-proposal`
  requires `expected_revision`, strict `fi|en` and the original
  expected-user/same-origin/CSRF gate. The exact owner-bound saved
  workspace must remain an editable draft with no browser receipt,
  the job must still be source-current, and the original employer
  description fingerprint must match. Both the stored draft
  revision AND the set of approved facts are rechecked after
  generation; a concurrent edit/revocation fails closed.
- Response is `Cache-Control: private, no-store`. It contains only
  the private draft text and explicit `saved=false`,
  `review_required=true`, `employer_contacts=0` and
  `external_actions_performed=0`. This request is entirely local
  deterministic Python (not an Ollama, ObumAI or employer call).
- Client verifies the initiating account before AND after the
  request and refuses stale workspace revisions, reserved employer
  attempts or browser receipts. The text is inserted into the
  **editable cover letter only**; the uploaded CV and approved
  profile facts are not modified. Existing dirty-edit confirmation
  prevents accidental loss of a personally edited letter.
- The applicant must review the draft and explicitly click the
  existing **Save changes** control; only then can the original
  download/browser/partner review process advance.

## Existing final-action safety gate reused and extended

The original `smartploy/browser_handoff.py:PLACEHOLDERS` blocks unfinished
English review prompts. The same compiled pattern is also imported by the
atomic `verified_employer_submit_preflight` used by independent employer
rights and one-use submit reservations. SP38 extends **that one shared
guard** to Finnish `[Kerro...]`, `[Lisää...]`, `[Oma nimi]`,
`[Täydennä...]`, `[Kirjoita...]` and `[Esimerkki...]` prompts.
An unfinished Finnish letter is now rejected before browser handoff AND
before an employer submit claim can be reserved, even when its
applicant has approved genuine job-related skills. A fully edited
Finnish letter remains eligible for the existing separate rights/review
checks. This is **not** a new final-action permission.

## Proof and tests

- Pure Python: job-specific Python/SQL approved evidence selected;
  unrelated approved Ruby, delivery experience, education and
  unapproved language excluded; Finnish template uses explicit
  structured language and original name, English can be requested
  even for a Finnish job; long statements never partially included;
  hostile employer instructions do not become candidate claims.
- Real PostgreSQL + first-party OIDC two-subject fixture with the
  same email address: only the original owner can generate a
  proposal; client-supplied wrong user, cross-site/cross-origin,
  stale revision, unsupported language and extra send fields rejected.
  Proposed text leaves saved revision, CV and letter UNCHANGED;
  the original immutable employer claim ledger remains empty.
- React: button works even when Ollama is disabled; CV remains
  unmodified; no saved document write until explicit user Save;
  declined dirty-edit confirmation does not lose personal wording;
  post-request account switch cannot show another applicant's text;
  an employer attempt reservation disables redrafting.
- Typed client: one owner-bound no-upload POST with expected revision,
  input validation and zero employer payload.
- Existing PDF/DOCX, local AI and original application tests must
  remain green; no migrations or new runtime dependencies required.
- Exact PR-head GitHub 5/5 and independently merged-main 5/5
  receipts are required before marking source delivery Done.

## Reused versus scratch

**Reused**: approved profile fact model, existing explainable
`score_candidate` matching, original job store/currentness and
workspace fingerprint, `new_workspace` across selected/automatic
paths, document update/export, identity/CSRF, original React editor
account checks, and OIDC/Postgres fixtures. **New**: a bounded
evidence projection, two language templates, a read-only-in-effect
signed-in language-preview action, two buttons, and tests. No
additional model, source connector, browser agent, external
permission, database migration or worker. No independently measured
engineering time saved.

## Deployment limits

This is code, not a claim of a live release. Native ObumDelivery
must still qualify an immutable reviewed SHA; the existing guarded
OVH rollout must prove the same image, current source health and
signed-in ZITADEL two-account acceptance. Public `/healthz`
was reachable during the previous SP36/SP37 checks but did not
attest a recent Git SHA. The operator-controlled employer final
submit mode remains OFF unless separately authorized. A prepared
CV/letter is **not** a submitted job application or a provider ACK.
