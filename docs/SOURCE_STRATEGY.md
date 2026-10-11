# Finland source strategy

Smartploy uses heterogeneous source adapters. "Job board" does not imply "scrapeable".

## Initial source classes

| Source | Planned mode | Current state |
| --- | --- | --- |
| Kuntarekry | authorized employer RSS/XML feed | adapter implemented; feed URL must be provisioned outside source |
| Työmarkkinatori / Job Market Finland | credentialed P67 v2 API | adapter implemented; disabled until KEHA onboarding/credentials |
| LinkedIn | manual/share/email/approved official integration | no scraping/browser-bot connector |
| Duunitori | manual/import until supported interface verified | review |
| Valtiolle.fi | manual/import until supported interface verified | review |
| Direct employer / ATS pages | SmartRecruiters / Lever public posting APIs | adapters implemented; tenant registry required |

## Kuntarekry boundary

Kuntarekry currently states that employers can obtain RSS/XML feeds through the employer service.
Smartploy therefore does not assume a globally public feed URL.

The adapter:
- requires an explicitly configured authorized feed URL;
- defaults to HTTPS and `kuntarekry.fi`/subdomain allowlisting;
- rejects IP-literal/non-allowlisted feed targets before network access;
- does not follow redirects;
- limits response size and request time;
- rejects XML DTD/entity declarations;
- never persists the configured feed URL query string as job evidence;
- records a durable source-health result for every poll.

Official references:
- https://kuntarekry.fi/fi/tyonantajalle/
- https://kuntarekry.fi/en/for-employers/

## Adapter requirements

Every adapter must define:
- source ID and source class;
- allowed acquisition mode;
- terms/permission review state;
- poll cadence/rate limits;
- raw snapshot/evidence retention;
- first seen / last seen / last verified;
- source health;
- parser version;
- canonical application URL;
- source-specific external ID where available.

A successful zero-result poll is recorded as a healthy run with `item_count=0`. A connector error is
recorded separately and must not be interpreted as "there are zero jobs".


## Job Market Finland / Työmarkkinatori boundary

Smartploy supports the official Job Market Finland job-posting retrieval interface version 2 through
KIPA P67. It does not scrape Job Market Finland pages.

Official onboarding and technical references:

- https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/interfaces-for-job-postings
- https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/interfaces-for-job-postings/retrieval-interface-description-and-instructions
- https://tyomarkkinatori.fi/jobpostingprovider/documentation/KIPA-search-jobpostings-en.html
- https://tyomarkkinatori.fi/en/instructions-and-support/interfaces/interfaces-for-job-postings/terms-of-use-for-job-market-finlands-job-posting-apis

The adapter is disabled unless JOBMARKET_FINLAND_API_ENABLED=true and a
JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY is supplied. Test and production endpoints are exact-allowlisted;
redirects and endpoint overrides outside the official hosts/path are rejected.

Incremental polling queries PUBLISHED and ARCHIVED separately using the modified interval. Omission from
a partial PUBLISHED result never closes a job. ARCHIVED records retire a known source external ID.

Job Market Finland terms require the displayed original-source attribution, so Smartploy preserves:
"Source: Job Market Finland's customer information system".

The same terms prohibit forwarding retrieval-interface postings to third parties without separate
permission. Smartploy therefore marks these postings external-AI-forwarding restricted by default:
they can be discovered, scored and displayed, but cannot enter ObumAI application preparation until
that processing basis is explicitly cleared.

When an ARCHIVED posting is received, Smartploy redacts that source occurrence. If the canonical job is
also independently backed by another current source, Smartploy rebuilds the canonical record from the
remaining source rather than closing the independent listing.


## Direct employer ATS sources

Smartploy supports explicit read-only employer tenants for SmartRecruiters, Lever and Greenhouse.

SmartRecruiters uses its public Posting API under:
`https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings`.

Lever uses its published Postings API under either:
- `https://api.lever.co/v0/postings/{SITE}`
- `https://api.eu.lever.co/v0/postings/{SITE}`

Greenhouse uses the public Job Board API at:
- `GET https://boards-api.greenhouse.io/v1/boards/{BOARD_TOKEN}/jobs?content=true`

**Greenhouse public-only boundary:** The adapter uses only the documented unauthenticated GET listing endpoint. It never calls the job-application POST endpoint, accepts Basic Auth keys, or guesses missing application URLs. Only explicitly published external job postings are accepted; prospect-only records with an explicit null `internal_job_id` are excluded. A failed, truncated or malformed listing cannot retire previously stored vacancies. `updated_at` is a modification timestamp, **not** a publishing date. The result displays Greenhouse source attribution and links to the public `absolute_url` application page. Work arrangements stay **unknown** when the structured board response does not state them.

Greenhouse may publish city-only `location.name` values (for example, `Espoo`) without a country. If an operator wants those jobs included, explicitly review and configure city names (`Espoo`, `Helsinki`) alongside the country term (`Finland`). The adapter does **not** infer that an arbitrary city is Finnish from employer-wide offices. Office country data is only consulted when the advertised location itself is missing, `Remote`, or unspecified.

The new provider is **code-supported only**: no live Greenhouse employer is activated by this change. An operator must select and review each board's terms, attribution/redistribution permissions and any allowed polling cadence before manually adding it to the private tenant registry. Public GET availability alone does not establish permission to redistribute content or forward it to cloud AI; `external_ai_forwarding_allowed` stays false unless separately approved.

Smartploy never accepts an arbitrary provider base URL. Operators configure a provider and tenant slug;
the adapter constructs the exact supported host/path.

Tenant configuration is loaded from either:
- `SMARTPLOY_PUBLIC_ATS_SOURCES_JSON`, or
- `SMARTPLOY_PUBLIC_ATS_SOURCES_FILE`.

The example registry is `config/public_ats_sources.example.json`. The local
`config/public_ats_sources.json` path is ignored by Git.

Each tenant explicitly declares:
- employer label;
- employer sector: public / private / unknown;
- whether external AI forwarding has been reviewed and allowed.

The AI-forwarding value defaults to false. Public availability of a job posting does not automatically
grant Smartploy permission to send its contents to an external AI provider.

### Location filtering safety

When `location_terms` are configured for an employer, SmartPloy compares them **only**
against structured job location/country fields using whole-place/word boundaries.
The explicit `FI` and `Finland` terms are equivalent for country matching.
For example, `fi` must not accept a Swedish office simply because the word
`Office` contains those letters, and `Finland` must not match `Finlandia`.

Unconfigured employers remain unfiltered. Terms are not inferred from role
descriptions or employer names. Configure Finnish sources deliberately and
inspect the filtered/active counts before enabling a changed location policy.
A fully successful snapshot may retire no-longer-in-scope source occurrences;
failed/partial polls must never retire existing jobs. Take a verified database
backup and review the source-diff/retirement impact before production rollout.

### Exhaustive snapshot rule

SmartRecruiters and Lever listing calls are treated as exhaustive public snapshots only after every
page/detail request succeeds. After a successful complete snapshot Smartploy retires previously active
external posting IDs that are absent. If any page, detail, parse, normalization, or duplicate-ID check
fails, retirement is skipped.

The same provider external ID remains bound to one Smartploy canonical job even when the employer edits
the description enough to change the content-derived duplicate fingerprint.

Official references:
- https://developers.smartrecruiters.com/docs/posting-api
- https://developers.smartrecruiters.com/docs/endpoints
- https://developers.smartrecruiters.com/docs/objects
- https://github.com/lever/postings-api
- https://docs.greenhouse.io/job-board.html (public GET vs credentialed POST)


## Opt-in source freshness acceptance

A source can remain marked `healthy` after its last successful poll becomes
stale. For the live job-discovery rollout, use the **optional**, read-only
age gate without breaking legacy readiness:

~~~bash
python scripts/check_ats_readiness.py --require-healthy --require-jobs --require-fresh-hours 6
~~~

- `--require-fresh-hours` accepts a finite 0.25–168 hour threshold and exits
  nonzero if any configured source is not healthy, lacks a timezone-aware
  completed/successful poll timestamp, has a date unexpectedly in the future,
  or exceeds the age threshold. Both the worker last-completed time and the
  source last-successful time must be sufficiently recent.
- Existing `--require-healthy` and `--require-jobs` semantics are unchanged
  when the freshness flag is omitted. A healthy zero-result poll remains healthy;
  `--require-jobs` separately requires actual selected job discovery.
- Only source IDs, safe health states, timestamps, counts and coarse freshness
  classifications appear in the report. It never prints source URLs with
  credentials, raw provider errors, job descriptions, CVs or tokens.
- This gate **does not** trigger polling, re-enable a source, retire a job,
  update a table, change OAuth/Cloudflare policies or submit an application.
  Staleness should lead to diagnosis of worker scheduling, source permission,
  rate limits and upstream changes before any production action.

**Not a real-world relevance metric:** a recent successful feed proves the
source was polled; it does not prove a listing is a good match for a particular
applicant. Job freshness and the offline synthetic search evaluation in
`docs/SEARCH_QUALITY_EVALUATION.md` are independent checks.
