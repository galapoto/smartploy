# SmartPloy REUSE-CHECK — copy for every code-producing change

**Status:** REVIEW REQUIRED before writing/replacing functionality or importing a dependency. Fill all relevant fields. A prior implementation in SmartPloy or ObumAI takes precedence over writing a new one. See [master plan](PROJECT_PLAN.md) §§11–18 and [source audit](REUSE_FIRST_AUDIT_2026-10-18.md).

| Evidence field | Required answer |
| --- | --- |
| Requirement and user-visible acceptance | |
| Owner, account/tenant, applicant and target ATS boundary | |
| SmartPloy main file/function, commit/blob inspected | |
| SmartPloy integrated PR and live open feature PRs inspected | |
| ObumAI Core/application/browser module/API inspected, commit/blob | |
| Other relevant internal agent/owned repo/draft branch inspected | |
| External GitHub/YouTube/TikTok repo candidates traced to actual source | |
| Chosen upstream canonical repo / immutable COMMIT / EXACT FILE / blob | |
| Exact file/subtree LICENSE text and copyright/NOTICE retained | |
| Dependency SBOM, transitive licenses, fonts/templates/trademarks | |
| Employer/ATS site and endpoint authorization/terms/rate limits | |
| Network requests, telemetry, remote model, CV/PII/cookie egress | |
| Browser permissions, CSP, session isolation, secrets, malware/SSRF | |
| Existing unit/browser/security/negative test evidence (exact SHA/CI) | |
| What source already does; what is actually missing | |
| Planned bounded adapter and any independent code; why reuse wins | |
| No unauthorized LinkedIn/Indeed access, CAPTCHA/MFA bypass or bot evasion | |
| Verified account-scoped fact/consent/permission and revocation | |
| Submit one-shot reserve/uncertain outcome/manual stop | |
| Attach actual document bytes, version/hash and employer readback | |
| Employer receipt classification (confirmed / observed / ambiguous / blocked) | |
| Tests to add; synthetic and authorized real employer acceptance | |
| Security/licensing reviewer and dated decision | |
| Decision REUSE / SMALL ADAPT / API BRIDGE / REJECT / NEW CODE | |
| Estimate avoided custom effort; actual hours/tests/regressions after review | |
| Exact ObumDelivery status, preview, production deploy SHA and rollback | |

## Mandatory negative-case checklist

- [ ] Unauthorized or restricted ATS/site/endpoint, wrong profile or active browser tab, unexpected redirect/iframe
- [ ] Revoked consent, wrong user and two-user account switching, expired login and stale credentials
- [ ] Fabricated or unsupported candidate fact, ambiguous salary/visa/sponsorship/EEO/legal attestation
- [ ] Hidden/changed/conditional React field, unsupported locale, prompt injection from posting
- [ ] Missing/wrong/modified/encrypted/oversized file, version or hash mismatch, re-rendered input
- [ ] CAPTCHA, OTP/MFA, blocked source, rate limit; stop without bypass
- [ ] Duplicate attempt, two-worker race, crash after send, network timeout after submit => UNKNOWN; no automatic retry
- [ ] Forged thank-you text or browser click labeled non-authoritative; no invented employer receipt
- [ ] Denied unauthorized PII/LLM egress, overbroad extension permission, cross-tenant cache, insecure telemetry
- [ ] Source/package transitive license, NOTICE, dependency vulnerability and provenance checked

**Any missing license, contradictory license, exposed applicant secret, unsupported right or consequential ambiguity = HOLD.** Merely modifying incompatible or unlicensed source is NOT lawful reuse. Do not import protected code; independently implement only publicly described requirements if appropriate and after documenting the independent design.

**Release evidence is staged:** SOURCE → LICENSE/SAFETY → SYNTHETIC → EXACT-HEAD OBUMDELIVERY → APPROVED PREVIEW → REAL AUTHORIZED EMPLOYER → CONFIRMED RECEIPT → TRUSTED OVH RELEASE. A PASS earlier in this sequence never implies a later PASS. Record failures, skips and unknowns without suppressing them.

**No applicant or employer data belongs in GitHub issues, model logs or third-party services without separately approved processing and source permissions.**
