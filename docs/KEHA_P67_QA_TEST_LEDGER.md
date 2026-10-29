# KEHA P67 v2 QA integration — living test evidence ledger

**Project:** Komplyint Oy / SmartPloy · **Provider:** KEHA Centre / Työmarkkinatori · **Source:** `job-market-finland`  
**Environment under test:** **QA only**, `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings`  
**Evidence reviewed:** User-supplied Linux terminal outputs received on **2026-10-28 and 2026-10-29**. Exact execution times were not captured; do not manufacture timestamps. **10 operator checks: 6 local/control/network PASS, 4 BLOCKED; 0 authenticated KEHA API successes.**  
**Overall status:** **HOLD — authenticated P67 POST and job retrieval remain unverified.** The Linux Mint network still times out at TCP/443 (QA-008). The separate OVH host now reaches KEHA over TLS (QA-009) **and** its unauthenticated **POST** receives HTTP 401 (QA-010), demonstrating that POST reaches an HTTP authentication/access-control layer. The subscription key has not been sent from OVH; no authorized job retrieval is proven.

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

**Inference supported by the evidence:** Linux Mint can use other HTTPS services but times out on KEHA QA TCP/443. OVH successfully completed TCP/TLS; HEAD produced 404 (QA-009), and unauthenticated POST produced 401 (QA-010). Thus the OVH origin can reach an HTTP authentication/access-control layer on the POST route. **Key validity, API response contract, actual vacancy counts, and KEHA approval of OVH's test egress are still unverified.** Exact cause of the Linux Mint block remains unknown. Do not enable production workers.

**Recommended next action:** keep the QA key on the original Linux Mint tester; use a temporary **SSH tunnel/SOCKS proxy through OVH** so authenticated QA POSTs can egress from the known-working OVH network without writing the key into the production server's filesystem, process environment or service configuration. Test the tunnel without credentials first, then run the existing database-free SP60 script in a short-lived local process if the tunnel and SOCKS support are confirmed. Only aggregate/redacted receipts may enter GitHub. KEHA should still be asked to confirm allowed egress origins and rotate the previously screenshot-exposed QA key. Never send the key in email.

## Independent network retest — 2026-10-29 (not from the QA operator IP)

**Separate evidence type: external, unauthenticated network diagnostics.**
These checks were launched by the assistant from **different execution
networks**, not the operator's Linux Mint computer or its outbound IPv4.
The KEHA subscription key was **not** transmitted or loaded into any
of these requests. They do not replace QA-001..QA-008 and do not add to
the count of **10 operator checks / 0 authenticated KEHA QA successes**.

| ID | Origin and test | Observed outcome | Interpretation |
| --- | --- | --- | --- |
| EXT-001 | Remote web-fetch service, fresh GET to `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings` | `timeout` | The external fetch path did not obtain an API HTTP response. This is not proof that the operator's allowlisted IP can/cannot connect. |
| EXT-002 | Same remote service, fresh GET to `https://api-qa.ahtp.fi/` | `proxy_error` | Proxy-layer failure; no usable KEHA API status or authentication verdict. |
| ENV-001 | Isolated assistant execution container, 2026-10-29T11:06:42Z, IPv4 unauthenticated HEAD to QA host and `github.com` control with `curl --noproxy '*'` | Both reported `curl: (6) Could not resolve host`, HTTP `000` | Local tool environment has no usable external DNS, so this probe **does not test KEHA reachability**. Do not forward it as evidence of a KEHA outage. |

**Conclusion:** No provider-backed progress and **no authenticated KEHA
job-posting retrieval** as of this retest. The actual operator **retested from their own Linux machine on 2026-10-29**
(QA-008) and again observed a TCP/443 timeout. KEHA's QA allowlisting or
destination routing remains unverified; do not assert that the API key has
been accepted or rejected. QA-009 showed OVH TLS reachability; QA-010 subsequently returned unauthenticated HTTP 401 for OVH POST. Neither proves key acceptance. Append a new
`QA-011` entry for the next sanitized operator result and update the P67 acceptance matrix;
do **not** overwrite the earlier failures.

## Eight-scenario QA acceptance matrix

| ID | Test scenario | Current evidence | Required live-acceptance proof |
| --- | --- | --- | --- |
| P67-01 | Reach endpoint, authenticate QA key and receive accepted HTTP response | **BLOCKED** for authenticated POST: Linux Mint timeout QA-003/004/006/008; OVH HEAD transport QA-009 PASS and unauthenticated POST HTTP 401 QA-010 PASS, but no key-accepted HTTP response | Sanitized `qa_reachable`, both request success flags or an authenticated HTTP receipt |
| P67-02 | Retrieve PUBLISHED postings | **NOT RUN** live; **LOCAL PASS** via MockTransport | Live `published_query_passed=true` and count; if zero, explicitly note no data returned |
| P67-03 | Retrieve ARCHIVED postings | **NOT RUN** live; **LOCAL PASS** via MockTransport | Live `archived_query_passed=true` and count; if zero, note the observed interval |
| P67-04 | Modified-time windows, empty-response behavior, bounded limits | **NOT RUN** live; **LOCAL PASS** | Successful short and longer windows without incorrect claim of newly discovered jobs |
| P67-05 | `fi`, `sv`, `en` posting language handling | **NOT RUN** live; **LOCAL PASS** | Valid returned language fields, if present; no need to force non-existent data |
| P67-06 | Normalize required fields: employer, title, location, application URL, original-source attribution | **NOT RUN** live; **LOCAL PASS** | Non-sensitive schema validation on actual QA payload; report counts, not raw postings |
| P67-07 | Duplicates, incremental updates and archived-posting retirement/redaction | **NOT RUN** live; **LOCAL PASS** in isolated source/Postgres tests | Controlled QA fixture sequence or provider-supported data, with no production database writes |
| P67-08 | Errors, credential secrecy, third-party AI/terms restrictions, no employer actions | **NOT RUN** live; **LOCAL PASS** for code protections | Sanitized negative control and verified QA-specific behavior; no secret, CV or job content in evidence |

**Evidence caveat:** The SP60 QA smoke deliberately performs **no DB writes** and reports only counts. It cannot, by itself, prove P67-06 and P67-07 on real KEHA data. Perform any deeper integration test on a separate disposable QA database with provider-permitted test data, not the live SmartPloy PostgreSQL instance, and do not publish raw provider records.

## Existing automated software evidence (separate from real QA)

- **Reused:** original `JobMarketFinlandAdapter` exact host allowlist, `KIPA-Subscription-Key` header, incremental PUBLISHED/ARCHIVED parser, source attribution, source retirement, `external_ai_forwarding_allowed=false`.
- **SP60 added:** isolated `scripts/probe_jobmarket_finland_qa.py`, safe error categories, production-vs-QA isolation gate and MockTransport negative controls.
- **Merged code:** [PR #222](https://github.com/galapoto/smartploy/pull/222), main commit `dcb4c974fa272a489582aa0a6f23fbe0f2afc544`.
- **Exact PR-head CI:** [run 40696033120](https://github.com/galapoto/smartploy/actions/runs/40696033120) — 5/5 successful.
- **Independent merged-main CI:** [run 40696723421](https://github.com/galapoto/smartploy/actions/runs/40696723421) — 5/5 successful: **1,236 Python/PostgreSQL tests**, 3 additional synthetic AutoApply tests, 217 React, 80 browser companion, 61 Chromium; synthetic Docker/OIDC/evidence PASS. **No authenticated KEHA QA traffic** occurs in these CI runs.
- Production access for the API is **not yet granted**. No real user AutoApply submission or production deployment is proven by this ledger.

## How to update after each subsequent run

For every operator output, append exactly one new receipt row **QA-011, QA-012, ...**, retaining all earlier failures for traceability. Add the result to the corresponding `P67-0x` row; change **NOT RUN → PASS** only on provider-backed evidence and note whether the count was zero. Capture the actual UTC timestamp *when available*, exact test command (excluding secrets), QA endpoint, sanitized status/error, small counts, environment, and any blocker/next action.

Never replace historical failures with later successes. Never turn a synthetic mock test into a provider acceptance claim. Do not store subscriber keys or residential/test-device IPs in this public repository.

**Companion Finnish email draft:** [KEHA P67 QA evidence — reply template](KEHA_P67_QA_REPLY_FI.md). Update its observed-results section from this ledger before sending and clearly distinguish the *network unblock request* from the later *production credential request*.

## References

- [SP60 deployment and QA boundary](SP60_KEHA_P67_QA_ACCESS.md)
- [Original adapter and terms](JOBMARKET_FINLAND.md)
- [Official P67 specification](https://tyomarkkinatori.fi/jobpostingprovider/documentation/KIPA-search-jobpostings-en.html)
