# Finland source strategy

Smartploy uses heterogeneous source adapters. "Job board" does not imply "scrapeable".

## Initial source classes

| Source | Planned mode | Current state |
| --- | --- | --- |
| Kuntarekry | authorized employer RSS/XML feed | adapter implemented; feed URL must be provisioned outside source |
| Työmarkkinatori / Job Market Finland | credentialed official API | blocked until organisation onboarding/credentials |
| LinkedIn | manual/share/email/approved official integration | no scraping/browser-bot connector |
| Duunitori | manual/import until supported interface verified | review |
| Valtiolle.fi | manual/import until supported interface verified | review |
| Direct employer / ATS pages | API/feed/direct adapter where permitted | per-provider review |

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
