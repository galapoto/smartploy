# SP76 — KEHA P67 production credentials: secure activation and acceptance

**Date:** 30 October 2026. **Baseline:** SmartPloy `main` `7808d055c69630ecb440e8460bf24753ed31ab33` (SP75, 5/5 merged-main CI).
**Plan subpart:** SP21 P0-A: nationwide current-job discovery, P0-C: correct source lifecycle and freshness, independent of employer AutoApply rights.

## New external permission — what changed

Komplyint Oy received an email from `tmt-rajapinnat@keha-keskus.fi` dated **30 October 2026**, granting **production** access to Työmarkkinatori's **job-posting search (hakurajapinta)** and providing a separate production endpoint and `KIPA-Subscription-Key` through a time-limited secure message. The owner shared **masked placeholders**, not the credential itself. This supersedes the QA-only authorization state recorded by SP60 and QA-013; it **does not** establish that any production request has succeeded or that a worker can access the data.

According to [KEHA's official P67 v2 technical documentation](https://tyomarkkinatori.fi/jobpostingprovider/documentation/KIPA-search-jobpostings-fi.html), the *canonical* production endpoint is `https://api.ahtp.fi/kipa/p67/v2/jobpostings`; search uses HTTPS `POST`, `KIPA-Subscription-Key`, and NDJSON. If a privately delivered endpoint differs, **do not use an override**, redirects, HTTP, or a proxy to bypass validation; verify it directly with KEHA.

There are two separate permissions: **reading source job postings** (newly granted) and **sending applications to employers** (NOT granted by KEHA). Neither a successful job search nor a private AutoApply draft constitutes employer submission.

## Security / KEHA terms

- Never paste the production secret, raw headers, individual job payloads or private IP address into ChatGPT, GitHub, CI, frontend Javascript, Cloudflare Pages, tickets, screenshots or release receipts. Store it only on the authorized OVH host in the **existing gitignored `deploy/personal/env` file with owner-only permissions** (or an equivalent encrypted secret store), without keeping it in shell history. Back up or transfer the secure message into a password manager before its expiry; rotate if it has been exposed.
- Production credentials belong to the production-only `https://api.ahtp.fi/` origin. **Never** use the former QA credential. QA and production must not be mixed.
- Original-source attribution must remain visible. KEHA requires withdrawn/archived listings to be removed promptly; do not treat an empty incremental modified window as a full inventory or leave stale jobs searchable. Keep external-AI forwarding forbidden for KEHA-derived postings without further permission.
- KEHA's [terms](https://tyomarkkinatori.fi/ohjeet-ja-tuki/rajapinnat/tyopaikkailmoitusten-rajapinnat/tyomarkkinatorin-tyopaikkailmoitusten-rajapintojen-kayttoehdot) restrict third-party redistribution and using their job dataset to market/advertise a service without permission. Do not imply official KEHA endorsement or origin.

## Fast, safe operator sequence

1. In the **private OVH host's** untracked `deploy/personal/env`, stage exactly `JOBMARKET_FINLAND_ENVIRONMENT=production` and `JOBMARKET_FINLAND_ENDPOINT=https://api.ahtp.fi/kipa/p67/v2/jobpostings`. Put the *new production* `JOBMARKET_FINLAND_KIPA_SUBSCRIPTION_KEY` there securely. Keep `JOBMARKET_FINLAND_API_ENABLED=false` while testing. **Do not** put the secret in `env.example`, a URL, GitHub Actions, or shell argument; do not set the production worker enabled yet.
2. In a *private environment that has loaded only those approved variables*, run the new **database-free**, **read-only** production probe, first **without flags**. Its receipt reports `status=offline_configuration_only`, credential presence but zero network/DB writes; this is **not** evidence of KEHA authorization.
3. On OVH (previously able to reach the KEHA QA host), run `python3 -m scripts.probe_jobmarket_finland_production --execute --minutes 30`. It makes exactly two bounded HTTPS POST searches, `PUBLISHED` and `ARCHIVED`, using the existing audited P67 adapter, then reports **aggregate counts only**, without opening PostgreSQL. No auto retries. A zero-count success demonstrates successful authentication for that window, **not** a nationwide inventory. **Do not run this command directly from a CI pipeline.**
4. Keep the worker off on any `hold` result. `PRODUCTION_AUTHORIZATION_OR_IP_ACCESS_DENIED` indicates a 401/403: confirm the *production* key and originating OVH egress/IP allowlist privately with KEHA; `PRODUCTION_NETWORK_OR_TLS` indicates transport/TLS failure; `PRODUCTION_RESPONSE_CONTRACT_INVALID` indicates a schema mismatch; rate limits/upstream errors require KEHA policy review. Never print raw response data to debug publicly.
5. **Only after live `production_search_reachable` acceptance** and an independently reviewed exact-SHA OVH release: have the production operator set `JOBMARKET_FINLAND_API_ENABLED=true` in the same protected env, preserve `JOBMARKET_FINLAND_ENVIRONMENT=production`, and run the existing guarded `deploy/personal/scripts/deploy.sh` procedure. The existing `preflight.sh` checks the exact endpoint, key presence, image/runtime separation, authenticated identity and release controls. Restart/recreate the *worker* only through the trusted release; toggling a host variable does **not** change a running container.
6. Collect **real, redacted evidence** from the scheduled worker `source:job-market-finland`: last success and failed statuses, PUBLISHED discovered/filtered/blocked counts, ARCHIVED retired counts, zero unauthorized AI forwarding, correct public attribution and current-vs-closed search behavior. Confirm source ingestion in SmartPloy with a signed-in user; the probe alone doesn't write jobs.
7. Initial feed coverage: the original incremental worker begins with only a **120-minute lookback** when no prior success exists; this will **not** backfill all currently open jobs across Finland. Validate an operator-reviewed historical/backfill strategy and safe API load limits before declaring broad national coverage. Do not multiply pollers or request unbounded intervals. Retirements must still be processed promptly.
8. Full product release remains separately blocked until **native ObumDelivery/Woodpecker exact-head receipt**, immutable approved OVH SHA with **matching API `/healthz` and web `/release.json`**, signed-in CV → matches → explicit Manual/Assisted/AutoApply → draft → observed outcome acceptance. Provider-specific employer final sends still require independent permission/consent and are unrelated to KEHA read access.

## Reuse-first ledger

| Item | Action |
| --- | --- |
| `smartploy/sources/jobmarket_finland.py` | **REUSED UNCHANGED**: already approved v2 POST/NDJSON, fixed QA/production HTTPS hosts, protected key, normalized FI/SV/EN fields, redacted model and terms flags |
| `smartploy/sources/jobmarket_finland_polling.py` | **REUSED UNCHANGED**: original PUBLISHED+ARCHIVED, retirements, original attribution and lifecycle; no remote new crawler |
| `smartploy/worker_runtime.py`, `scripts/poll_jobmarket_finland.py` | **REUSED UNCHANGED**: existing gated worker and source DB ingestion, not executed by this PR |
| `scripts/probe_jobmarket_finland_qa.py` | **REUSED DESIGN**: SP60 disabled-worker, two-POST, count-only, bounded acceptance, but without permitting QA keys/URLs in production |
| `scripts/probe_jobmarket_finland_production.py` | **NEW MINIMAL**: production-only credential check and redacted, zero-database read-only acceptance with no activation side effects |
| `tests/test_jobmarket_finland_production_smoke.py` | **NEW TESTS**: exact host, count-only real adapter, empty result semantics, 401/403, 429/503, malformed NDJSON, QA/worker rejection, key non-disclosure and no DB |
| `docs/JOBMARKET_FINLAND.md`, env template, master plan | **ADAPTED**: superseded QA approval and explicit safe production operator sequence |
| `morluto/rea` | **REA_NOT_APPLICABLE**: all relevant legally authorized first-party source, API schema, credentials-handling contracts and test fixtures are available; no opaque binary to reverse engineer. REA **not** run, no third-party code copied and `savings=unknown` |

## Evidence classification

**DONE (source):** production-only, no-secret acceptance CLI; synthetic tests; updated operator plan and license guardrails.

**IN PROGRESS until measured:** exact PR-head CI and separate merged-main CI; real production probe on OVH using credentials placed privately by the operator.

**BLOCKED (live):** key is **not installed by this chat or GitHub PR**, no production HTTP receipt/real jobs imported by this source work; independent approved OVH release/native CI and signed-in AutoApply acceptance. Production source **must remain OFF** until actual proof and approved rollout. Follow [production issue #232](https://github.com/galapoto/smartploy/issues/232).
