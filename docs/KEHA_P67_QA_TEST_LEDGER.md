# KEHA P67 v2 QA integration — living test evidence ledger

**Project:** Komplyint Oy / SmartPloy · **Provider:** KEHA Centre / Työmarkkinatori · **Source:** `job-market-finland`  
**Environment under test:** **QA only**, `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings`  
**Evidence reviewed:** User-supplied Linux terminal outputs received on **2026-10-28 and 2026-10-29**. Exact execution times were not captured; do not manufacture timestamps. **13 operator checks: 9 PASS (including one repeat and the first authenticated QA probe), 4 earlier origin-network BLOCKED; 1 authenticated probe covering 2 successful P67 POST searches.**  
**Overall status:** **QA AUTHENTICATED SEARCH SUCCESS (EMPTY 30-MINUTE WINDOW); NONEMPTY POSTING VALIDATION AND PRODUCTION ACCESS STILL HOLD.** The original Linux Mint direct TCP connection fails (QA-008), but a temporary SSH SOCKS tunnel through OVH works (QA-012). QA-013 used the existing database-free SmartPloy P67 adapter to successfully complete **two authenticated POST searches** for PUBLISHED and ARCHIVED. Both returned **zero records modified in the last 30 minutes**. This does **not** establish that the nationwide API has no job postings or that nonempty response parsing works.

> **Privacy:** This public document intentionally excludes the subscription key, user's home public IPv4, IP-to-person linkages, private network configuration, request headers, raw job descriptions and CVs. The outgoing IP was identified in the user's private test session and can be communicated *directly to KEHA* as needed. Do not paste the key into issues, PRs, support emails or test output. Consider rotating it because the original credential appeared in screenshots.

## Evidence classification

- **PASS:** observed success for the specific stated condition, with an output receipt.
- **BLOCKED:** test attempted, but precondition prevents its real acceptance.
- **NOT RUN:** not tested against KEHA QA; do not infer success from mocked calls.
- **LOCAL PASS:** verified using SmartPloy or GitHub's *synthetic* test harness only, **not** proof of actual KEHA authorization.
- **Target acceptance threshold:** the following eight scenarios are a **SmartPloy engineering recommendation**, **not a KEHA-stated number or mandatory test quota**. KEHA decides when evidence suffices for production access.

## Observed operator tests (2026-10-28 and 2026-10-29; exact times unavailable)

| Receipt ID | Check | Evidence (non-secret excerpt) | Finding |
| --- | --- | --- | --- |
| QA-001 | SP60 test CLI installed | `python3 -m scripts.probe_jobmarket_finland_qa --help` showed `--execute` and `--minutes` in `~/smartploy-keha-qa` virtual environment | **PASS**: local script exists and is callable |
| QA-002 | Offline configuration and key presence | `status=offline_configuration_only`; `credential_present=true`; `network_requests=0`; `live_qa_verified=false` | **PASS**, config only; **not** confirmation that KEHA accepted the key |
| QA-003 | Live 30-minute PUBLISHED+ARCHIVED probe | `python3 -m scripts.probe_jobmarket_finland_qa --execute --minutes 30` → `status=hold`; `reason=QA_NETWORK_OR_TLS`; `live_qa_verified=false` | **BLOCKED** before receiving an API response. No posting count was established |
| QA-004 | Unauthenticated direct QA HTTPS reachability | `curl -I` → `curl_exit=28`; `HTTP=000`; DNS ~0.032 s; TCP and TLS **not established**; 10 s connect timeout | **BLOCKED** at TCP/443. This is not a 401/403 key rejection |
| QA-005 | Control: outbound public HTTPS / IPv4 | `curl -4 -I https://github.com` → `HTTP=200`, TCP ~0.068 s, TLS ~0.109 s | **PASS**: general outbound IPv4 HTTPS working |
| QA-006 | QA destination forced IPv4 | `curl -4 -I https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings` → `HTTP=000`; connect timeout ~10 s; no TLS | **BLOCKED**: reproduced with IPv4, so IPv6 preference alone cannot explain the failure |
| QA-007 | Identify test host's public outbound IPv4 | `curl -4 -fsS https://api.ipify.org` returned one public IPv4 | **PASS**: value retained privately for KEHA's IP allowlist check; **not published here** |
| QA-008 | 2026-10-29 repeat QA HTTPS connection on original Linux test machine, forced IPv4 | `curl -4 -sS -I --connect-timeout 10 --max-time 15` → `curl: (28)` after 10002 ms; `HTTP=000`; `TCP=0.000000s`; `TLS=0.000000s`; `curl_exit=28` | **BLOCKED**: fresh TCP/443 timeout; no HTTP response, TLS handshake, API authentication or job retrieval. Public egress IP was **not rechecked** during this attempt. |
| QA-009 | 2026-10-29 separate OVH host `obum-core-01`, forced-IPv4 HEAD to QA P67 path, **without subscription key** | `curl -4 -sS -I --connect-timeout 10 --max-time 15` → `HTTP=404`; `TCP=0.103818s`; `TLS=0.148471s`; `curl_exit=0` | **PASS — TCP/TLS transport only.** OVH HTTPS succeeded. The P67 specification requires **POST**; a 404 on HEAD does not establish POST routing, authorization or job retrieval. No production changes. |
| QA-010 | 2026-10-29 separate OVH host `obum-core-01`, unauthenticated forced-IPv4 **POST** to exact KEHA QA P67 URL with `{}` body | `curl -4 -sS --request POST --header 'Content-Type: application/json' --header 'Accept: application/x-ndjson' --data '{}' --output /dev/null` → **`HTTP=401`**, `TCP=0.021172s`, `TLS=0.065590s`, `curl_exit=0` | **PASS — POST reaches an HTTP authentication/access-control layer** from OVH. No subscription key provided, so 401 does **not** prove credential acceptance, request-body correctness or job retrieval. Response body intentionally suppressed; no production changes. |
| QA-011 | 2026-10-29 repeat of **the same no-key OVH POST control**, `obum-core-01`, exact QA URL and empty JSON body | `HTTP=401`; `TCP=0.021644s`; `TLS=0.078375s`; `curl_exit=0` | **PASS — repeat reachability only**, not a new functional scenario. Confirms reproducible POST response from OVH; no subscription key was present and no job records retrieved. |
| QA-012 | 2026-10-29 Linux Mint key-free POST through a temporary **SSH SOCKS5 tunnel** at `127.0.0.1:1081` to OVH, using `curl -4 --socks5-hostname` | `HTTP=401`; `TCP=0.000103s` (**local SOCKS connection timing**); `TLS=0.351804s`; `curl_exit=0` | **PASS — end-to-end tunneled HTTPS POST reachability only**. HTTP 401 without subscription key confirms connectivity to an authentication/access-control layer via OVH egress. Does not authenticate key or prove job data retrieval. Secret was not entered. |
| QA-013 | 2026-10-29 **authenticated live QA P67 two-search probe**, Linux Mint local virtualenv through temporary SSH SOCKS5 tunnel via OVH; `python3 -m scripts.probe_jobmarket_finland_qa --execute --minutes 30` | `status=qa_reachable`; `qa_endpoint_verified=true`; `published_query_passed=true`; `archived_query_passed=true`; `published_posting_count=0`; `archived_posting_count=0`; `modified_window_minutes=30`; `production_database_writes=0`; `employer_applications_sent=0`; `external_ai_forwarding=false` | **PASS — QA credential accepted and both bounded, read-only P67 POST searches completed**. Zero matching records **in this modified window**: provider response parsing of *nonempty* PUBLISHED/ARCHIVED data, language fields, attribution on actual records and retirement lifecycle are **NOT validated**. No job content/key persisted or printed, no production use. |

**Inference supported by the evidence:** Linux Mint direct HTTPS to KEHA remains blocked, but a temporary SSH SOCKS route via OVH works. The original key-free OVH POST returned HTTP 401; in QA-013 the **actual P67 adapter, using the private QA key on Linux Mint, completed both PUBLISHED and ARCHIVED queries** through the tunnel and reported `qa_reachable`. This provides evidence of working QA authentication and the empty-result response contract. No provider records were present in the 30-minute modified interval, so nonempty payload parsing, national job availability, post-archive lifecycle and source attribution on live data remain unproven. Do not enable production workers or assume the QA key also works in production.

**Recommended next action:** repeat the **same original database-free SP60 probe** with a **120-minute** modified window as QA-014, through the **same** working Linux Mint SOCKS tunnel, with the QA worker still disabled and the key privately entered into a short-lived subshell. Broader successful empty responses will validate time-window handling but not nonempty posting parsing; if real postings are returned, capture **counts only** and evaluate schema/attribution in an isolated disposable QA environment under KEHA's terms. Confirm with KEHA whether additional test cases are needed for production credential approval. Request QA key rotation because it previously appeared in screenshots.

## Independent network retest — 2026-10-29 (not from the QA operator IP)

**Separate evidence type: external, unauthenticated network diagnostics.**
These checks were launched by the assistant from **different execution
networks**, not the operator's Linux Mint computer or its outbound IPv4.
The KEHA subscription key was **not** transmitted or loaded into any
of these requests. They do not replace QA-001..QA-008 and do not add to
the count of **13 operator checks / 1 authenticated QA probe, 2 successful POST searches**.

| ID | Origin and test | Observed outcome | Interpretation |
| --- | --- | --- | --- |
| EXT-001 | Remote web-fetch service, fresh GET to `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings` | `timeout` | The external fetch path did not obtain an API HTTP response. This is not proof that the operator's allowlisted IP can/cannot connect. |
| EXT-002 | Same remote service, fresh GET to `https://api-qa.ahtp.fi/` | `proxy_error` | Proxy-layer failure; no usable KEHA API status or authentication verdict. |
| ENV-001 | Isolated assistant execution container, 2026-10-29T11:06:42Z, IPv4 unauthenticated HEAD to QA host and `github.com` control with `curl --noproxy '*'` | Both reported `curl: (6) Could not resolve host`, HTTP `000` | Local tool environment has no usable external DNS, so this probe **does not test KEHA reachability**. Do not forward it as evidence of a KEHA outage. |

**Historical conclusion from earlier network retest:** no authenticated KEHA search had succeeded as of QA-012. **Subsequent QA-013 supersedes that readiness assessment:** a Linux Mint-local, SSH SOCKS-proxied test succeeded with the private QA key, and the P67 adapter returned `qa_reachable` for both PUBLISHED and ARCHIVED searches with zero matching postings in the 30-minute window. Continue to append the next result as **QA-014**, preserving all earlier failed connectivity receipts. No production authorization or nonempty job-posting validation is implied.

## Eight-scenario QA acceptance matrix

| ID | Test scenario | Current evidence | Required live-acceptance proof |
| --- | --- | --- | --- |
| P67-01 | Reach endpoint, authenticate QA key and receive accepted HTTP response | **PASS (QA-013):** actual adapter returned `qa_reachable`, two authenticated POSTs successful over Linux Mint SOCKS route. Direct home-origin network remains blocked. | Sanitized `qa_reachable` and the two successful request flags observed |
| P67-02 | Retrieve PUBLISHED postings | **PASS — query/empty response only (QA-013):** `published_query_passed=true`, `published_posting_count=0` over 30 minutes. **Nonempty posting extraction NOT TESTED**. | Need provider-backed nonempty data or agreed fixture to validate extraction |
| P67-03 | Retrieve ARCHIVED postings | **PASS — query/empty response only (QA-013):** `archived_query_passed=true`, `archived_posting_count=0` over 30 minutes. **Nonempty archival extraction NOT TESTED**. | Need provider-backed nonempty data or agreed fixture to validate extraction |
| P67-04 | Modified-time windows, empty-response behavior, bounded limits | **PARTIAL live PASS (QA-013):** valid empty 30-minute bounded window. A different window has **not** yet been tested live. | Repeat same probe with 120-minute window (QA-014) and compare sanitized counts |
| P67-05 | `fi`, `sv`, `en` posting language handling | **NOT RUN** live; **LOCAL PASS** | Valid returned language fields, if present; no need to force non-existent data |
| P67-06 | Normalize required fields: employer, title, location, application URL, original-source attribution | **NOT RUN** live; **LOCAL PASS** | Non-sensitive schema validation on actual QA payload; report counts, not raw postings |
| P67-07 | Duplicates, incremental updates and archived-posting retirement/redaction | **NOT RUN** live; **LOCAL PASS** in isolated source/Postgres tests | Controlled QA fixture sequence or provider-supported data, with no production database writes |
| P67-08 | Errors, credential secrecy, third-party AI/terms restrictions, no employer actions | **PARTIAL live PASS (QA-013):** reported no production DB writes, AI forwarding, applicant accesses or employer submissions; negative controls remain synthetic. | Verify provider-specific terms/negative paths separately, with sanitized receipts |

**Evidence caveat:** The SP60 QA smoke deliberately performs **no DB writes** and reports only counts. It cannot, by itself, prove P67-06 and P67-07 on real KEHA data. Perform any deeper integration test on a separate disposable QA database with provider-permitted test data, not the live SmartPloy PostgreSQL instance, and do not publish raw provider records.

## Existing automated software evidence (separate from real QA)

- **Reused:** original `JobMarketFinlandAdapter` exact host allowlist, `KIPA-Subscription-Key` header, incremental PUBLISHED/ARCHIVED parser, source attribution, source retirement, `external_ai_forwarding_allowed=false`.
- **SP60 added:** isolated `scripts/probe_jobmarket_finland_qa.py`, safe error categories, production-vs-QA isolation gate and MockTransport negative controls.
- **Merged code:** [PR #222](https://github.com/galapoto/smartploy/pull/222), main commit `dcb4c974fa272a489582aa0a6f23fbe0f2afc544`.
- **Exact PR-head CI:** [run 40696033120](https://github.com/galapoto/smartploy/actions/runs/40696033120) — 5/5 successful.
- **Independent merged-main CI:** [run 40696723421](https://github.com/galapoto/smartploy/actions/runs/40696723421) — 5/5 successful: **1,236 Python/PostgreSQL tests**, 3 additional synthetic AutoApply tests, 217 React, 80 browser companion, 61 Chromium; synthetic Docker/OIDC/evidence PASS. **No authenticated KEHA QA traffic** occurs in these CI runs.
- **QA-013 (2026-10-29):** actual authenticated P67 QA calls succeeded twice (PUBLISHED and ARCHIVED), both zero records in 30-minute modified interval; **zero** production DB writes and employer actions. This live acceptance evidence is distinct from prior synthetic CI.
- Production access for the API is **not yet granted**. No real user AutoApply submission or production deployment is proven by this ledger.

## How to update after each subsequent run

For every operator output, append exactly one new receipt row **QA-014, QA-015, ...**, retaining all earlier failures for traceability. Add the result to the corresponding `P67-0x` row; change **NOT RUN → PASS** only on provider-backed evidence and note whether the count was zero. Capture the actual UTC timestamp *when available*, exact test command (excluding secrets), QA endpoint, sanitized status/error, small counts, environment, and any blocker/next action.

Never replace historical failures with later successes. Never turn a synthetic mock test into a provider acceptance claim. Do not store subscriber keys or residential/test-device IPs in this public repository.

**Companion Finnish email draft:** [KEHA P67 QA evidence — reply template](KEHA_P67_QA_REPLY_FI.md). Update its observed-results section from this ledger before sending and clearly distinguish the *network unblock request* from the later *production credential request*.

## References

- [SP60 deployment and QA boundary](SP60_KEHA_P67_QA_ACCESS.md)
- [Original adapter and terms](JOBMARKET_FINLAND.md)
- [Official P67 specification](https://tyomarkkinatori.fi/jobpostingprovider/documentation/KIPA-search-jobpostings-en.html)
