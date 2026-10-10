# Finland source strategy

Smartploy uses heterogeneous source adapters. "Job board" does not imply "scrapeable".

## Initial source classes

| Source | Planned mode | Bootstrap state |
| --- | --- | --- |
| Kuntarekry | public RSS/XML feed | first live connector candidate |
| Työmarkkinatori / Job Market Finland | credentialed official API | blocked until organisation onboarding/credentials |
| LinkedIn | manual/share/email/approved official integration | no scraping/browser-bot connector |
| Duunitori | manual/import until supported interface verified | review |
| Valtiolle.fi | manual/import until supported interface verified | review |
| Direct employer / ATS pages | API/feed/direct adapter where permitted | per-provider review |

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

An adapter returning zero results when it is normally active must be distinguishable from a healthy
source with genuinely zero matching jobs.
