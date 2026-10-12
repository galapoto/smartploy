# ATS source coverage regression review (SP-12)

SmartPloy already exposes a **sanitized, read-only** source readiness JSON
report. This offline tool compares two reports for loss of coverage, staleness,
and unexpectedly large decreases in Finnish job listings. It does not poll
employers, change database contents, retire jobs, deploy an image, forward data
to ObumAI or authorize applications.

## Comparison contract

- Detect an unexpected removed source, and flag any newly configured source
  for separate source-owner/terms approval (including Greenhouse boards).
- Check previously healthy sources for degraded states or regressions in their
  last-success timestamps. Optionally require that each existing source has
  completed a newer successful poll.
- Compare employer-level Finnish-matching postings at the last poll and
  cross-source active unique jobs. These numbers need not equal one another
  because multiple source records can refer to the same job.
- Flag decreases of 50% or more by default. Job counts naturally fluctuate:
  a flagged change means **human review required**, not a confirmed outage.
- Honor an explicit false freshness-gate result from the candidate snapshot.
  A missing freshness check is not silently treated as fresh.

## Private operator procedure

On the OVH host, collect a sanitized baseline **before** deploying a separately
approved immutable release. Keep both files in the restricted deploy-state
directory and do not put them into GitHub or share raw snapshots.

~~~bash
(
  set -Eeuo pipefail
  umask 077
  cd /srv/obum/stacks/smartploy
  SNAP=/srv/obum/data/smartploy/deploy-state
  install -d -m 700 "$SNAP"
  sudo docker exec smartploy-worker-1 \
    python scripts/check_ats_readiness.py > "$SNAP/ats-before.json"
  chmod 600 "$SNAP/ats-before.json"
)
~~~

After the guarded release, source scheduling has had time for one successful
poll per approved employer, and operator source permission/backup checks
pass, collect the later report and compare.

~~~bash
(
  set -Eeuo pipefail
  umask 077
  cd /srv/obum/stacks/smartploy
  SNAP=/srv/obum/data/smartploy/deploy-state
  sudo docker exec smartploy-worker-1 \
    python scripts/check_ats_readiness.py > "$SNAP/ats-after.json"
  chmod 600 "$SNAP/ats-after.json"
  python -m scripts.compare_ats_readiness \
    "$SNAP/ats-before.json" "$SNAP/ats-after.json" \
    --max-job-drop-percent 50 --require-new-poll
)
~~~

The optional **--require-new-poll** flag should only be used after every
source's reviewed polling interval has elapsed. Omit it for an immediate
post-release comparison if you only need to check health, counts and
source identities. The comparison never initiates a poll.

Exit code 0 = pass; 3 = manual review required; 2 = malformed, oversized,
duplicate-ID or out-of-order evidence. A review result must not trigger
automatic rollback, source retirement or external employer actions.

Add **--json** for a machine-readable summary with safe source IDs and
classification labels, but no raw provider errors, CVs, job descriptions,
tokens or file contents. Store full sanitized snapshots privately.

## CI and evidence scope

~~~bash
pytest -q tests/test_ats_coverage_compare.py
python -m scripts.compare_ats_readiness --help
~~~

Tests use fictional snapshots to cover removed/new sources, healthy-to-failed
regression, major vs normal vacancy changes, optional re-poll validation,
missing/regressed timestamps, invalid input, bounded file reads, CLI exit
codes and the absence of untrusted personal fields in the output.

Passing CI is **not** a production deployment, a live applicant-browser test,
or permission to aggregate a new employer's listings. The release operator
must still review actual source metrics, source terms/attribution, private
backup and running image evidence. Follow SP-12 approval issue #99 and real
signed-in browser acceptance issue #91.

This independent report is a **coverage regression** check, not a real-world
job-relevance metric. The ranking benchmark is documented separately in
docs/SEARCH_QUALITY_EVALUATION.md.
