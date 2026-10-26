# SP45 — Running OVH browser companion release attestation

**Date:** 26 October 2026
**Baseline:** SP44 main `804c5176fe7251e20e1e5977df27b9daec91da85`
**Part:** SP21 P0-C production activation and Fast Fleet / ObumDelivery
source→artifact→deploy→verify safety chain.

## Release blocker

SP44 created a first-party installable Chrome companion ZIP, checksum and
link within Application Studio. Exact GitHub CI proved the production-style
Caddy Docker image could serve the correct download. However the guarded
OVH deploy script only asserted API health, running container images,
worker task, auth and database. An old/missing/HTML-disguised ZIP could be
deployed while still recording a successful `deployed-sha`.

## What is now enforced

Reuse the original `deploy/personal/scripts/deploy.sh` lock, exact
origin/main immutable SHA admission, backup/migration, OIDC preflight,
recreate, health/image/Agent Zero gates. Before committing a new
`deployed-sha`, the existing script now invokes
`assert-companion-release.sh <validated-public-host> <local-web-port>`.

This new **read-only** gate:
1. Packages the current checkout's original 15 allowlisted, permission-
   restricted extension sources into a deterministic ZIP in a **temporary
   directory**, using the existing SP44 stdlib builder.
2. Fetches the running local Caddy's static
   `/smartploy-apply-companion.zip` and `.zip.sha256` endpoints from
   **127.0.0.1** with the expected validated Host. No public API,
   employer request, login, cookie or applicant data.
3. Requires non-cached `Cache-Control: no-store`, exact one-line lowercase
   SHA-256 sidecar format, `sha256sum -c`, and byte-for-byte `cmp`
   of the running ZIP against the freshly built exact source ZIP.
4. Rejects HTTP error, missing ZIP, SPA `index.html`, malicious host
   or port, wrong checksum, unreviewed ZIP bytes even with a matching
   attacker-modified checksum, and unsolicited third-party redirects.
5. Only then prints `companion_release_verified=true` and a non-sensitive
   exact ZIP SHA-256.

The original `release-evidence.sh` **independently invokes the same
check**, and writes only the two trusted fields to its permission-600
signed-SHA evidence artifact. No new release state, external service,
secret or persistent package is required.

## Native ObumDelivery reuse

The preinstalled Woodpecker isolated-build web-browser stage still
runs the original React, MV3 Node and Chromium tests. SP44 now invokes
a Python stdlib packaging prebuild from that same stage. SP45 explicitly
ensures Python3 exists in the isolated Playwright image (install via
Ubuntu apt if absent) before calling `npm run build`. It does not grant
the CI worker OVH SSH, production secrets or any deploy permission.
The final Woodpecker receipt remains a safe **production gate HOLD**
until the independent approved OVH deployment executes.

## Regression proof

- `tests/test_companion_delivery_gate.py`: actual offline loopback HTTP
  server serves the original real packaged ZIP and SHA with Caddy-style
  headers. Verifier returns verified=true and exact digest. Seven
  negative controls reject stale SHA, fully altered ZIP with matching
  altered SHA, missing ZIP, non-cache-safe response, redirect to
  untrusted host, HTML pretending to be ZIP and malicious sidecar path.
- Source contract checks deployment verifies companion **before** writing
  `deployed-sha` and that release-evidence persists ZIP attestation.
- The original full Compose CI recreates web image and performs the
  **same** verifier against running synthetic Caddy prior to backup/
  restore and release-evidence; that evidence must include
  `companion_release_verified=true` and a 64-char SHA.
- Exact PR-head 5/5; merge only after green; independent merged main 5/5.

## Still not claimed

This is source hardening of the operator's existing guarded deploy command,
not evidence of a real OVH deployment. Native Woodpecker execution and
real signed-in Chrome/consenting-employer acceptance are separate checks.
No provider submission or verified employer acknowledgment is created;
all non-employer-approved final clicks remain blocked. Production remains
unverified until its exact running release revision and first-party
ZIP download are actually observed on the public domain.
