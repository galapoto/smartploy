# Repository development instructions

Preserve existing approval, privacy, security and release controls. This file grants no access to other repositories or production resources.

## REA-FIRST-001 — owner P0 reuse-first mandate (29 October 2026)

**MANDATORY for all future approved feature work, website/webapp/API design, software architecture, security architecture, tests and substantial refactoring.** Before coding, inspect existing first-party source/history and licensable upstream implementations, then make and record an REA suitability decision for any comparable authorized app, executable, website, API recording or binary. Consult the [ObumDelivery canonical directive](https://github.com/obumai/obum-delivery/blob/main/docs/REA_FIRST_MANDATORY_REUSE_STANDARD.md) and [decision/evidence template](https://github.com/obumai/obum-delivery/blob/main/docs/REA_REUSE_DECISION_TEMPLATE.md) where accessible.

**Use REA where applicable:** Prefer static/read-only analysis of authorized examples; use its CLI/MCP/browser/JavaScript/native/recorded-API evidence to recover behavior, interfaces, architecture and test cases. Record `REA_APPLIED`, `REA_NOT_APPLICABLE` or `REA_BLOCKED`, with target permission, exact source/version, evidence, unknowns and reasons. Not-applicable is a legitimate documented outcome; an unavailable REA dependency must not indefinitely halt a small useful release.

**Reuse maximally, build minimally:** (1) reuse fit-for-purpose, appropriately licensed code as-is; (2) clean and adapt it; (3) extend only missing functionality; (4) implement remaining code independently with tests. Reuse up to 100% of *relevant, permitted* code, never blindly copy entire projects. REA's own MIT license does not license third-party programs it inspects. Do not copy protected source/assets, bypass controls, import unsafe dependencies or use unanalyzed binaries in production.

**Required proof every run/PR:** plan and baseline SHA; reuse candidates and exact paths/licenses; REA status, tool revision, permitted target, observed evidence and limitations; reused/cleaned/adapted versus new code; executable feature and negative/security tests; actual CI/deploy evidence; measured engineering time with comparable baseline or `savings=unknown`; DONE / IN PROGRESS / NOT STARTED / BLOCKED. Recovered pseudocode, generated code or a green static scan alone never proves user-visible capability.

**Existing authority prevails:** Preserve this repo's stricter security/privacy, protected branch, project-plan/Director GO, independent owner, cost, scope, CI and release controls. This instruction grants no cross-repository write permission, credentials, live trading, real-exam inspection, unauthorized reverse engineering or production deployment. ObumDelivery/Woodpecker remains the authoritative CI where already designated. This is a mandatory engineering-method rule, **not proof that REA is installed or CI enforcement is deployed**.
