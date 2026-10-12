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
approved immutable release. Keep both files in an operator-owned private directory, separate from
root-owned deployment/backup state, and do not put them into GitHub.

~~~bash
(
  set -Eeuo pipefail
  umask 077
  cd /srv/obum/stacks/smartploy
  SNAP="$HOME/.local/share/smartploy-ats-acceptance"
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
  SNAP="$HOME/.local/share/smartploy-ats-acceptance"
  sudo docker exec smartploy-worker-1 \
    python scripts/check_ats_readiness.py > "$SNAP/ats-after.json"
  chmod 600 "$SNAP/ats-after.json"
  # The OVH checkout is root-managed; use root only to read its script.
  # The comparison itself performs no network calls or database writes.
  sudo /usr/bin/python3 \
    /srv/obum/stacks/smartploy/scripts/compare_ats_readiness.py \
    "$SNAP/ats-before.json" "$SNAP/ats-after.json" \
    --max-job-drop-percent 50 --require-new-poll
)
~~~

### Root-managed OVH checkout: permission recovery

On `obum-core-01`, the repository may be readable only by root. Running
`python -m scripts.compare_ats_readiness` as the normal `ubuntu` user then
raises `PermissionError` for the source script **after deployment has already
completed**. Do not loosen repository/file permissions, re-run deployment, or
copy private source files into a public location merely to finish this check.

For an **immediate** after-deploy comparison (no fresh poll cycle required),
run the validated, standard-library-only script under `sudo`:

~~~bash
(
  set -Eeuo pipefail
  umask 077
  REPO=/srv/obum/stacks/smartploy
  SNAP="$HOME/.local/share/smartploy-ats-acceptance"
  SHA=fc94e78e779650e781277ee1056ec92cd26a6e98
  test "$(sudo git -C "$REPO" rev-parse HEAD)" = "$SHA"
  test -s "$SNAP/before.json"
  test -s "$SNAP/after.json"
  sudo /usr/bin/python3 "$REPO/scripts/compare_ats_readiness.py" \
    "$SNAP/before.json" "$SNAP/after.json" \
    --max-job-drop-percent 50 --json
)
~~~

This is a recovery example for the reviewed 12 October 2026 release
`fc94e78`, not permission to deploy a moving branch. Result `pass` is
evidence of the configured source-comparison policy only. Result
`review_required` (exit 3) must be inspected privately; neither result
automatically rolls back the live stack. Permission errors must not be
misreported as deployment failures.

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
