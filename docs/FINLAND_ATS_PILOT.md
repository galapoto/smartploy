# Finland public employer ATS discovery pilot

SmartPloy can begin collecting real Finnish jobs without requiring access to
KEHA's credentialed national Job Market Finland API. **This is an opt-in
five-employer pilot**, not a full nationwide search engine.

## Verified published boards

These are public employer job-board pages reviewed on 11 October 2026.
Individual postings change, so do not promise a specific number or job category.

| Employer/source | Published job site |
| --- | --- |
| The Upright Project | https://jobs.lever.co/uprightproject |
| Brightly Works | https://jobs.lever.co/brightlyworks |
| Netlight | https://jobs.lever.co/netlight |
| Rovio | https://jobs.lever.co/rovio-2 |
| TSMG | https://jobs.lever.co/tsmg |

Lever official published Postings API:
https://github.com/lever/postings-api

The adapter only GETs the official HTTPS API
`https://api.lever.co/v0/postings/{tenant}`, never an arbitrary URL,
and never creates job applications. All external AI forwarding is disabled.

## Geography

Each pilot board has explicit allowlisted geographic keywords covering
Finland and selected Finnish cities. A dedicated `location_terms` option
filters **structured location/country fields only**: it does not search job
descriptions or treat a company headquartered in Finland as proof that all its
jobs are Finnish. The country code `FI` is accepted when `Finland` is among
the location terms. Unmatched/unknown locations are excluded.

On every successful exhaustive source snapshot, missing previously imported
external IDs are retired. A failed or incomplete snapshot never retires them.
Source health reports the total published count and exclusions separately.

This conservative filtering may omit valid remote positions without an
explicit Finnish location. Later versions should implement structured country
support for more ATS providers.

## Safe operator activation on obum-core-01

The service is **still disabled** until the operator runs the activation
steps. Do not paste private `deploy/personal/env` content into chat or GitHub.

After the merged pilot release is deployed and passes CI:

```bash
cd /srv/obum/stacks/smartploy || exit 1
sudo git fetch origin main
# Review and pin the exact approved commit SHA before changing production.
sudo git checkout --detach APPROVED_40_CHARACTER_SHA

# Step 1: review first (does not modify the env)
sudo python3 scripts/configure_finland_ats_pilot.py

# Step 2: explicit opt-in (edits only one setting in private env)
sudo python3 scripts/configure_finland_ats_pilot.py --apply

# Step 3: guarded deployment, which preserves PostgreSQL and all other stacks
sudo bash deploy/personal/scripts/preflight.sh
sudo bash deploy/personal/scripts/deploy.sh APPROVED_40_CHARACTER_SHA

# Step 4: verify exact running images, HTTPS and security boundaries
sudo bash deploy/personal/scripts/assert-running-images.sh APPROVED_40_CHARACTER_SHA
sudo bash deploy/personal/scripts/live-acceptance.sh
sudo bash deploy/personal/scripts/release-evidence.sh --online

# Step 5: check actual source polls without revealing environment secrets
sudo docker logs --since 5m smartploy-worker-1 --tail 40
```

Once the worker has polled (normally within tens of seconds) SmartPloy's
Job Sources and Find Jobs pages should show **real observed records**.
Do not claim success until actual source health and stored job totals are
verified. Individual upstream sources can legitimately return zero jobs.

### Rollback

The pilot staging command refuses to override an already-configured registry.
To disable the pilot, a privileged operator may edit only the following key
in `deploy/personal/env` (without touching PostgreSQL data):

```text
SMARTPLOY_PUBLIC_ATS_SOURCES_JSON=
```

Rerun production preflight and the guarded deploy at the pinned SHA.
Previously stored job records are retained for audit; job freshness should
still be reported truthfully.

## Outside this milestone

- Job Market Finland P67 API requires KEHA onboarding and credentials.
- Kuntarekry feeds require an authorized employer RSS/XML feed.
- ObumAI machine authentication and final applicant submissions are not enabled.
- This does not grant permission to use employer job text in external AI inference.
- This does not make employment recommendations before CV/profile evidence
  has been explicitly reviewed by the candidate.
