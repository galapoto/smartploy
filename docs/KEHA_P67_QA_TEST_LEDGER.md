# KEHA P67 v2 QA integration — living test evidence ledger

**Project:** Komplyint Oy / SmartPloy · **Provider:** KEHA Centre / Työmarkkinatori · **Source:** `job-market-finland`  
**Environment under test:** **QA only**, `https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings`  
**Evidence reviewed:** User-supplied Linux terminal output received on **2026-10-28**. The exact execution time was not captured; do not manufacture timestamps.  
**Overall status:** **BLOCKED — QA network TCP/443 timeout**. Authentication, posting retrieval, and live parser/lifecycle acceptance are **not yet verified**.

> **Privacy:** This public document intentionally excludes the subscription key, user's home public IPv4, IP-to-person linkages, private network configuration, request headers, raw job descriptions and CVs. The outgoing IP was identified in the user's private test session and can be communicated *directly to KEHA* as needed. Do not paste the key into issues, PRs, support emails or test output. Consider rotating it because the original credential appeared in screenshots.

## Evidence classification

- **PASS:** observed success for the specific stated condition, with an output receipt.
- **BLOCKED:** test attempted, but precondition prevents its real acceptance.
- **NOT RUN:** not tested against KEHA QA; do not infer success from mocked calls.
- **LOCAL PASS:** verified using SmartPloy or GitHub's *synthetic* test harness only, **not** proof of actual KEHA authorization.
- **Target acceptance threshold:** the following eight scenarios are a **SmartPloy engineering recommendation**, **not a KEHA-stated number or mandatory test quota**. KEHA decides when evidence suffices for production access.

## Observed operator tests (2026-10-28, exact times unavailable)

| Receipt ID | Check | Evidence (non-secret excerpt) | Finding |
| --- | --- | --- | --- |
| QA-001 | SP60 test CLI installed | `python3 -m scripts.probe_jobmarket_finland_qa --help` showed `--execute` and `--minutes` in `~/smartploy-keha-qa` virtual environment | **PASS**: local script exists and is callable |
| QA-002 | Offline configuration and key presence | `status=offline_configuration_only`; `credential_present=true`; `network_requests=0`; `live_qa_verified=false` | **PASS**, config only; **not** confirmation that KEHA accepted the key |
| QA-003 | Live 30-minute PUBLISHED+ARCHIVED probe | `python3 -m scripts.probe_jobmarket_finland_qa --execute --minutes 30` → `status=hold`; `reason=QA_NETWORK_OR_TLS`; `live_qa_verified=false` | **BLOCKED** before receiving an API response. No posting count was established |
| QA-004 | Unauthenticated direct QA HTTPS reachability | `curl -I` → `curl_exit=28`; `HTTP=000`; DNS ~0.032 s; TCP and TLS **not established**; 10 s connect timeout | **BLOCKED** at TCP/443. This is not a 401/403 key rejection |
| QA-005 | Control: outbound public HTTPS / IPv4 | `curl -4 -I https://github.com` → `HTTP=200`, TCP ~0.068 s, TLS ~0.109 s | **PASS**: general outbound IPv4 HTTPS working |
| QA-006 | QA destination forced IPv4 | `curl -4 -I https://api-qa.ahtp.fi/kipa/p67/v2/jobpostings` → `HTTP=000`; connect timeout ~10 s; no TLS | **BLOCKED**: reproduced with IPv4, so IPv6 preference alone cannot explain the failure |
| QA-007 | Identify test host's public outbound IPv4 | `curl -4 -fsS https://api.ipify.org` returned one public IPv4 | **PASS**: value retained privately for KEHA's IP allowlist check; **not published here** |

**Inference supported by the evidence:** name resolution works; general IPv4 HTTPS works; KEHA QA TCP/443 is unreachable from the test machine. Plausible causes include KEHA's IP allowlist, a firewall, or destination-specific routing. **We have not verified which**. It is premature to declare the key valid/invalid, claim a successful QA request, claim zero published vacancies, or enable the live production worker.

**Recommended next external action:** reply to the existing KEHA credentials email, quote the separate private outbound IPv4 (the user has it), and request confirmation/activation of TCP/443 access to the *QA* hostname. Ask whether additional networks or outbound IPs (including the later OVH worker) require allowlisting. Do not send the subscription key.

## Eight-scenario QA acceptance matrix

| ID | Test scenario | Current evidence | Required live-acceptance proof |
| --- | --- | --- | --- |
| P67-01 | Reach endpoint, authenticate QA key and receive accepted HTTP response | **BLOCKED** by QA-003/004/006 | Sanitized `qa_reachable`, both request success flags or an authenticated HTTP receipt |
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

For every operator output, append exactly one new receipt row **QA-008, QA-009, ...**, retaining all earlier failures for traceability. Add the result to the corresponding `P67-0x` row; change **NOT RUN → PASS** only on provider-backed evidence and note whether the count was zero. Capture the actual UTC timestamp *when available*, exact test command (excluding secrets), QA endpoint, sanitized status/error, small counts, environment, and any blocker/next action.

Never replace historical failures with later successes. Never turn a synthetic mock test into a provider acceptance claim. Do not store subscriber keys or residential/test-device IPs in this public repository.

**Companion Finnish email draft:** [KEHA P67 QA evidence — reply template](KEHA_P67_QA_REPLY_FI.md). Update its observed-results section from this ledger before sending and clearly distinguish the *network unblock request* from the later *production credential request*.

## References

- [SP60 deployment and QA boundary](SP60_KEHA_P67_QA_ACCESS.md)
- [Original adapter and terms](JOBMARKET_FINLAND.md)
- [Official P67 specification](https://tyomarkkinatori.fi/jobpostingprovider/documentation/KIPA-search-jobpostings-en.html)
