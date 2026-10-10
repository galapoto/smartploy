# Public employer ATS sources

## Purpose

Discover jobs at the original employer ATS whenever a supported public postings API exists. This
reduces dependence on aggregators and preserves provider posting identity.

The current connectors are read-only:
- SmartRecruiters Posting API
- Lever Postings API

Application-submission APIs are intentionally not implemented here.

## Registry

Example:

~~~json
[
  {
    "provider": "smartrecruiters",
    "tenant": "example-company",
    "label": "Example Company",
    "employer_sector": "private",
    "external_ai_forwarding_allowed": false
  },
  {
    "provider": "lever",
    "tenant": "example-company",
    "label": "Example Company",
    "stack": "eu",
    "employer_sector": "private",
    "external_ai_forwarding_allowed": false
  }
]
~~~

Tenant slugs accept only letters, digits and hyphens. No URL field exists, so a registry entry cannot
redirect Smartploy to an arbitrary host.

Configure exactly one:
- SMARTPLOY_PUBLIC_ATS_SOURCES_JSON
- SMARTPLOY_PUBLIC_ATS_SOURCES_FILE

For file-based deployments, copy config/public_ats_sources.example.json to an ignored local file such
as config/public_ats_sources.json.

## SmartRecruiters

Smartploy fetches the public posting collection in pages of at most 100 and then retrieves each posting
detail. It preserves:
- posting ID;
- posting/apply URLs;
- released date;
- employer;
- title and description;
- location / remote indicator;
- industry, department, function, experience and employment metadata;
- qualifications as source details, not automatically as mandatory requirements.

## Lever

Smartploy supports global and EU stacks. It paginates published postings with skip/limit and preserves:
- posting ID;
- hosted/apply URLs;
- title and plain descriptions;
- location, commitment, team, department and all locations;
- workplace type;
- salary range metadata.

EUR salary minimum/maximum values may populate Smartploy salary fields. Non-EUR ranges remain source
metadata and are not treated as EUR.

## External identity

Content fingerprints are useful for cross-source duplicate detection, but provider external IDs are
stronger for updates within one source. Before upserting a source observation, Smartploy checks for an
active source_id + source_external_id binding. If one exists, the new observation is rebound to the
existing canonical job even if its edited description would otherwise generate a different canonical
key.

Retired observations are excluded from this lookup.

## Retirement

A public ATS poll retires missing external IDs only after the adapter has successfully fetched the
entire current public snapshot. Any fetch/parser/normalization failure leaves existing jobs untouched.

## AI processing

external_ai_forwarding_allowed defaults to false per tenant. Enable it only after reviewing the
processing basis for that employer/source. Smartploy's existing preparation and ObumAI boundaries
enforce this flag.

## Operator command

~~~bash
export SMARTPLOY_DATABASE_URL='postgresql://...'
export SMARTPLOY_PUBLIC_ATS_SOURCES_FILE=config/public_ats_sources.json
python scripts/poll_public_ats.py
~~~

## References

SmartRecruiters:
- https://developers.smartrecruiters.com/docs/posting-api
- https://developers.smartrecruiters.com/docs/endpoints
- https://developers.smartrecruiters.com/docs/objects

Lever:
- https://github.com/lever/postings-api
