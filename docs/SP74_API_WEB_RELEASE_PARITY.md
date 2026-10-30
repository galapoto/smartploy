# SP74 — Exact API and public web release parity

**Date:** 2026-10-30  
**Source baseline:** `21d5b7fcdf94b0a7337aea8ccca00360e30d9299` (SP73 merged, 5/5 exact-main CI).  
**Plan:** SP21 P0 production activation / Gate 0: ensure the actual visible SPA and API both correspond to the *same reviewed immutable release*.

## Production incident addressed

The current public SmartPloy OIDC `/healthz` is `ok=true` but **does not expose `release_revision`**. The source API contract and deployment script already require the exact 12-character source SHA on the backend, yet there is no comparable static frontend fingerprint. A new API alongside a stale Caddy frontend can leave the applicant on an older/blank application flow while an API-only liveness test passes.

This is a source-side **release identity / safety improvement**, not a claim that the stale live service has been updated.

## Code changes and reuse ledger

| Source | Decision / change |
| --- | --- |
| Existing `smartploy/api.py /healthz` and `SMARTPLOY_APP_VERSION` | **REUSED UNCHANGED:** backend publicly exposes only the safe 12-hex reviewed build identity; no applicant or auth details |
| Existing image tag/APP_VERSION derivation in `deploy/personal/scripts/deploy.sh`, `Dockerfile`, `docker-compose.yml` | **ADAPTED:** feed identical immutable tag into both API and Caddy web build; no extra environment secret or container privilege |
| Existing first-party static Vite/Caddy image | **ADAPTED:** create `/release.json` with exactly `schema` and `release_revision`; exact file handler returns actual JSON or 404, not a SPA fallback, with `Cache-Control: no-store` |
| `smartploy/live_acceptance.py` | **REUSED/EXTENDED:** strict origin identity and policy check, exact API/web version matching, optional public HTTPS web parity; generic error output with no reflected payload |
| Existing `assert-running-images.sh` / `release-evidence.sh` / `live-acceptance.sh` | **REUSED:** Docker image IDs, backup checks, private OIDC and public API parity remain mandatory. SP74 adds `assert-web-release.sh` to the already guarded deploy/evidence flow |
| Original GitHub CI isolated production Compose smoke | **EXTENDED:** exercise the *real built Caddy static file and API* with matching release SHA. CI synthetic fixture is not production deployment |
| `web/scripts/package_release_manifest.py`, `deploy/personal/scripts/assert-web-release.sh` | **NEW MINIMAL:** deterministic no-secret static manifest and a read-only exact-SHA comparison at local origin, optionally public OIDC HTTPS |
| Tests | **NEW/EXTENDED:** manifest validation, empty/stale/extra fields, expected-version mismatch, symlink/injected data, public proxy mismatch, no-store header and real Compose smoke |
| `morluto/rea` | **REA_NOT_APPLICABLE**: both first-party API and web source, deploy infrastructure and acceptance contracts are already available and auditable. No opaque executable or unavailable third-party app to recover. REA not executed; no external code copied and no time savings invented |

## Acceptance contracts

- `release.json` contains only `{"release_revision":"<12lowerhex>","schema":"smartploy-web-release-v1"}`; local `dev` allowed **for unshipped developer builds only**. Production validation denies `dev`, missing/invalid/uppercase/mismatched or extra fields.
- The frontend built by the reviewed CI/deploy SHA must serve the real file directly from Caddy. Its HTTP response must be no-store. Missing file cannot be rewritten to `index.html` and accepted by a JSON parser.
- The API `/healthz` must be healthy and match immutable origin policy, with `release_revision` equal to the **same** exact reviewed SHA prefix as the local static web manifest.
- For Komplyint OIDC production, public TLS `https://smartploy.komplyint.fi/release.json` must also match the locally served manifest. Existing `live-acceptance.sh` independently validates **public API health**, private signed-out access and trusted OIDC redirects.
- Legacy Cloudflare Access is not opened to anonymous health or release endpoints: check only the local Caddy manifest and API behind its original Access gate.
- The new check cannot authorize a deployment. Existing exact source checkout, signed reviewer, identity policy, running image parity, private backups, worker proof, partner rights and separate signed-in acceptance still apply.
- The GitHub Compose smoke never handles a real user CV or production credentials and must not be cited as native Woodpecker or running OVH evidence.

## Completion / release gates

**Source done:** build-time public frontend version, exact parser, local and optional public SHA parity, check integrated in the guarded deploy and release-evidence steps, tests and documentation.

**CI required:** Exact-head 5/5 success (web, browser, Python/Postgres, Compose real serving, exact-checkout receipt) and separate merged-main CI.

**Production blocked:** ObumDelivery native SmartPloy enrollment still requires operator review and a real Woodpecker pipeline. Trusted OVH release must produce exact image, `/healthz`, `/release.json`, rollback and signed-in CV→job→review→provider-confirmed outcome receipts. Current live `/healthz` lacks a revision. The user’s existing watch for the earlier SP72 revision remains unchanged unless explicitly updated.

Tracking: [SmartPloy production issue #232](https://github.com/galapoto/smartploy/issues/232) and [ObumDelivery fleet issue #29](https://github.com/obumai/obum-delivery/issues/29).
