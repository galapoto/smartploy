# Bilingual search relevance: deterministic acceptance

SmartPloy's personalized search score measures **alignment with user-entered
search preferences**, not a confirmed candidate qualification or employer
eligibility result. Job-search criteria remain private to the owner profile,
separate from independently approved CV evidence.

## Supported, conservative bilingual role titles

The first explicit equivalence set matches these title families in both
directions (English/Finnish), using whole words and punctuation-safe phrases:

| English target | Finnish target |
| --- | --- |
| Data Analyst | Data-analyytikko |
| Business Analyst | Liiketoiminta-analyytikko |
| Software Tester | Ohjelmistotestaaja |
| Project Coordinator | Projektikoordinaattori |

This is **not** arbitrary translation or semantic AI inference. Only a full
role-family match is promoted; an extra job-family qualifier such as
"Manager" is not discarded. The system can still show other jobs under
"Explore more" or via explicit keyword matches. It never converts a matching
job title into an assertion that the applicant has that qualification.

A target job title that **explicitly says** Junior/Senior also conveys a
narrow seniority preference even when the separate dropdown is set to
"Any level". Known conflicting titles stay visible under "Explore more".
Unknown advertised levels stay discoverable with an uncertainty note.
If the user also saved a broader overlapping role (e.g. both "Junior Data
Analyst" and "Data Analyst") or both junior and senior targets, the matcher
does **not** silently invent a single-level restriction. A non-"Any"
experience-level dropdown remains the user's explicit controlling setting.

Finnish `vanhempi` (senior), `nuorempi` and `juniori` (entry) are
recognized *when explicit in a title*. Unknown seniority remains unknown.

## Language, location and work mode

Selected ad-language preferences are matched against structured labels:
English/englanti/EN, Finnish/suomi/FI, and Swedish/ruotsi/SV with supported
Finnish adjective/adverb forms. Unknown labels are marked unverified rather
than as a known mismatch. These labels do **not** imply the applicant speaks
the language.

Location comparisons use bounded place-name phrases rather than substrings:
Helsinki must not match "Helsinkiesque". A location label merely saying
"Remote" is not enough to establish location, so it remains unknown.
Work mode uses separately normalized remote/hybrid/on-site metadata.

## Reproducible verification

Run against local synthetic fixtures without external job boards, user data,
LLMs or employer submissions:

~~~bash
pytest -q tests/test_search_preferences.py
pytest -q tests/test_scoring.py
~~~

The test matrix covers translated target roles in both directions, explicit
Finnish junior/senior conflict, absent/unknown language tags, EN/FI/SV codes,
city boundaries, preserved general-mode behavior and private settings.

**Known limits**: Job titles and advertised language fields are not a substitute
for verifying degrees, work authorization, experience, actual spoken language,
skills or career-change eligibility. Free-text Finnish job descriptions may
use inflected terms or untranslated terminology outside this small vocabulary.
Use independent approved career evidence for fit, and manually review mandatory
requirements before any consequential job application.

Do not enable external employer actions or cloud AI based on these search
quality changes. Before production deployment, require all four exact-commit
CI checks, a guarded database backup and private source/edge acceptance.
