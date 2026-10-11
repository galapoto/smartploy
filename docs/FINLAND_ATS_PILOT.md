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

## TSMG network-timeout mitigation (11 October 2026)

The first live pilot imported ten Finnish jobs across four healthy boards.
TSMG's first request timed out at the prior global 15-second request timeout.
Its source-specific `request_timeout_seconds: 45` and `page_size: 50`
are an explicit *candidate mitigation*, not proof of a successful TSMG poll.
Other employers still use the original 15 seconds / 100 postings.

**Do not use a global timeout increase** merely to fix TSMG.
Published Lever location filtering cannot filter `country=FI`, so this fix
continues to download the complete paginated snapshot and then check
structured Finnish location/country fields. It does not silently drop
Finnish remote jobs identified through country code.

After the fix is reviewed, merged and checked out on `obum-core-01`,
the operator can upgrade only the original canonical five-source private
registry, without printing the registry or touching its database password:

```bash
cd /srv/obum/stacks/smartploy
sudo python3 scripts/configure_finland_ats_pilot.py --upgrade-tsmg-transport
sudo python3 scripts/configure_finland_ats_pilot.py --upgrade-tsmg-transport --apply
sudo bash deploy/personal/scripts/preflight.sh
sudo bash deploy/personal/scripts/deploy.sh REVIEWED_40_CHARACTER_SHA
sudo bash deploy/personal/scripts/assert-running-images.sh REVIEWED_40_CHARACTER_SHA
sudo bash deploy/personal/scripts/live-acceptance.sh
sudo bash deploy/personal/scripts/release-evidence.sh --online
sudo docker exec smartploy-worker-1 python scripts/check_ats_readiness.py
```

The upgrade refuses to change an operator-modified registry or an existing
custom source file. The real verification is a new TSMG source poll reporting
`healthy_with_matching_jobs` or `healthy_zero_matching_jobs`. If the
source still reports `network_timeout`, gather new failure evidence before
another change; do not make unbounded retries.

**Rollback:** at the same reviewed SHA, the operator may run
`sudo python3 scripts/configure_finland_ats_pilot.py --rollback-tsmg-transport --apply`
and redeploy with the guarded release process. This only reverts TSMG's
per-source tuning and preserves the other four feeds. Retiring jobs from
incomplete/failed snapshots remains prohibited.

## Outside this milestone

- Job Market Finland P67 API requires KEHA onboarding and credentials.
- Kuntarekry feeds require an authorized employer RSS/XML feed.
- ObumAI machine authentication and final applicant submissions are not enabled.
- This does not grant permission to use employer job text in external AI inference.
- This does not make employment recommendations before CV/profile evidence
  has been explicitly reviewed by the candidate.
