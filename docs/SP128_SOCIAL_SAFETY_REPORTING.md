# SP128 — Messaging safety report and operator review (feature-first contract)

Status: **SOURCE_READY** pending exact-head CI, independent privacy/security and moderation review, native Woodpecker qualification and actual authorized rollout. This is not a production or user-verified capability.

## User outcome

In SmartPloy's **Messages** screen, a signed-in recipient can choose **Report** on a received message, select Spam / Harassment / Scam / Impersonation / Other and optionally enter a short note. The server accepts reports only for the exact message that this verified person **received**, even if they subsequently block or unfollow the sender. The user sees the submitted status under **Connections → My safety reports**. Repeated submission is idempotent. Reporting never sends an employer application, posts publicly, bans an account or contacts the reported person.

An explicitly allowlisted operator sees **Message safety reports** in **Connections**, including a 240-character excerpt linked to the original message, a reason, optional reporter note and reviewed status. They can mark a report **Reviewed** (not "removed"/"account suspended"). Normal users cannot enumerate reports, read excerpts or change states. An empty operator allowlist fails closed; the UI does not claim a moderator is always online.

## Privacy and security controls

- Uses the existing FastAPI signed-in tenant binding and same-origin cookie CSRF gate; web mutations always send the verified `X-Smartploy-Expected-User-Id` precondition.
- No email, CV, job-application text, free-form message copy or social directory is added to the report ledger.
- A report requires `recipient_id = verified user ID`; sender/third-party report attempts produce a generic 404 without disclosing the message.
- Only `SMARTPLOY_OPERATOR_USER_IDS` (server-issued stable user IDs) grants operator access. No self-service moderator promotion, email role inference or header role.
- Message previews and reporter notes are strictly limited to verified operators; every API response has `private, no-store`.
- Reports are bounded to **20 new message reports per reporter per rolling 24 hours**, serialized across PostgreSQL workers. A repeat of the same message does not consume another quota.
- Operator review can mark only `open → reviewed`, idempotently; not deletion, automatic suspension, evidence destruction or disciplinary judgement.
- Existing account-quarantine inventory now counts reports where the affected user was reporter, reported user or reviewing moderator. Foreign keys cascade on account/message deletion. This is **not** a hard-purge certificate.
- DMs are **not end-to-end encrypted**. No realtime report alert, 24/7 moderation guarantee, attachment scanning, abuse machine learning or automatic bans are represented.

## Production acceptance and holds

1. Exact-head GitHub unit/PostgreSQL/Chromium/build/isolated-stack checks, followed by **native** Woodpecker qualification for the reviewed SHA. No synthetic result proves real accounts.
2. Independent privacy, abuse-response, operator assignment and documented data-retention review. Without an appointed responsive moderator, hold external launch of DMs/reporting rather than promising a monitored safety service.
3. Merge the dependent SP127 social feature first through authorized review. This SP128 PR is intentionally stacked on SP127 and must be independently qualified on the final combined main SHA.
4. Controlled release on `obum-core-01`: backup; apply migrations 031 and 032 in order; verify actual OIDC authentication, sender/recipient/moderator three-account access, private API boundaries, security headers, report creation and review, and rollback evidence.
5. Record `deployed-sha`, actual running image parity, live UI availability and operator sign-off. Only **USER_VERIFIED** may be called shipped.

## Reuse / REA evidence

Reused SmartPloy's existing operator allowlist, OIDC/Cloudflare verified principal binding, same-origin CSRF, private social message IDs and relational tenancy, Pydantic error validation, first-party React inbox/components, SQLite-free real PostgreSQL integration tests, synthetic browser acceptance and account-erasure inventory.

REA status: **REA_BLOCKED** — official `morluto/rea` MIT upstream documentation previously inspected; executable runtime/tool connection not available in this environment. No unauthorized analysis of WhatsApp, Facebook, LinkedIn or copying award-site protected code/assets. New code is first-party. Engineering time savings: **unknown**.

## Explicit feature boundaries

This is message safety reporting + review only, not a social public-feed system, direct third-party integration, push notification system, messenger calls, social recommendation engine or comprehensive moderation policy. Reporting remains independent of employer submission permissions and the CV-first apply journey.
