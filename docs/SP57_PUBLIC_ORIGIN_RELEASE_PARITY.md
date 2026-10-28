# SP57 — Block stale public ingress before certifying SmartPloy production

**Date:** 28 October 2026 · **Plan subpart:** SP21 P0-C production handoff and ObumDelivery release acceptance.
**Baseline:** merged SP56 `797e0d3c7af58ce525c697792d66c07bd0d7608f`.

## Observed production gap

Public `https://smartploy.komplyint.fi/healthz` was healthy but returned **no `release_revision`** in the read-only public probe. SP24 already implemented a validated, public 12-hex backend release fingerprint and existing local release scripts compare the checked-out Git SHA against the running image/loopback health. **Rebuild/reimplementation would be wasteful.** The missing live revision means that an exact running release cannot be independently attested from public access.

The original post-deploy `live-acceptance.sh` validated local health, public TLS/login and signed-out API protection but did not insist that the **public HTTPS `/healthz` host actually routed to the same revision as local HTTP**. A stale public Caddy target, DNS or proxy could pass those other shape checks while serving older code.

## Reuse vs new

**Reused (original first-party code):** `smartploy.live_acceptance.validate_origin_health`, exact immutable OIDC origin from `select-runtime-policy.sh` and `validate-runtime-policy.sh`, SP24 `release_revision` and existing Docker build SHA tagging, `deploy.sh` checkout+image+backup+agent+extension gates, public TLS/issuer/private API probes, owner-restricted legacy Cloudflare mode, and restricted `release-evidence.sh` state/sha256 sidecar.

**New (small fail-closed glue):**
- A pure validation function comparing strict lower-case 12-hex release IDs and both identity, storage, and external-action safety contracts for separate local and public health JSON.
- A bounded `curl` read of the exact allowlisted **public HTTPS** Komplyint OIDC `/healthz` (no redirect follows, accounts, secrets or tokens). The independent Python verifier allows only valid matching releases. It emits only the safe 12-hex value after success.
- The original online release evidence independently refuses absent/invalid public-vs-local proof and a public value different from `deployed-sha`. New fixed release fields are recorded for operator verification.
- The legacy Cloudflare Access profile **skips unauthenticated public release parity** rather than weakening owner-restricted access and never falsely marks it passed.

## Test/acceptance plan

- Synthetic valid matching public/local OIDC release; wrong/missing/invalid/uppercase/40-hex releases; stale public ingress; mismatched origin/service/storage/permissions/access; rejected legacy profile; CLI secret-safe nonzero behavior.
- Static and shell syntax proof that live acceptance is gated before success, without production secrets or runtime mutation; existing Python/PostgreSQL, React, companion, Chromium and isolated Docker CI must remain green.
- **Source qualification only until live operator proof.** An isolated CI Docker run does not verify real public DNS/TLS. Native ObumDelivery Woodpecker project is still `enabled: false`, so a native positive/negative exact source receipt and operator-approved OVH deployment remain unverified. Do not claim exact source is live just because this PR passes.
- Post-deploy verified public revision, full on-host SHA, owner-scoped two-account end-to-end QA and actual provider rights/ACK are independent mandatory gates. Generic unattended ATS employer submission remains unavailable.

**No new application engine, third-party source, model, database migration, dependency, external send or deployment performed in this code slice.**
