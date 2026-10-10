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

Smartploy supports explicit read-only employer tenants for SmartRecruiters and Lever.

SmartRecruiters uses its public Posting API under:
`https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings`.

Lever uses its published Postings API under either:
- `https://api.lever.co/v0/postings/{SITE}`
- `https://api.eu.lever.co/v0/postings/{SITE}`

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
