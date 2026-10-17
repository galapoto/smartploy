# Account-erasure quarantine (review-only; no public trigger)

SmartPloy stores private CV documents, structured approved evidence, local draft
workspaces, application-event histories, per-account search settings, consent,
session records and references to processing performed at ObumAI.

**This is a quarantine and inventory implementation, not completed erasure.**

## Atomic quarantine contract

Internal operator-only PostgresAccountErasureRepository.quarantine accepts an
already verified, exact user_id/profile_id pair. In one database transaction it:

1. Takes exclusive locks on the live user and profile, serializing with the
   existing consent-protected network dispatch lock. Lock timeout fails closed.
2. Disables account access, blanks the account email and metadata, revokes all
   OIDC sessions and scrubs their email/metadata. Ingress middleware already
   rejects disabled accounts; identity resolution and alias linking do not
   restore access or repopulate the email.
3. Revokes every still-active job-scoped ObumAI permission and records a
   redacted revision/event, atomically. A repeated quarantine does not mint
   duplicate grant-withdrawal events.
4. Registers a stable quarantine request, then inventories recorded provider
   jobs and durable sending/uncertain client request IDs as unresolved
   processor-erasure obligations (migration 018). It **does not** call provider
   delete/POST, cancel in-flight remote work, or claim that any deletion
   happened outside SmartPloy.

The non-privileged result contains only request ID, counts and explicit
"no erasure yet" flags; provider IDs remain internal/operator-only.

## Read-only local data inventory

inspect_quarantined_account provides scoped counts of identities/sessions,
approved facts, CVs, saved jobs, search preferences, workspaces/browser
receipts, preparations/applications/events, consent/history and one-shot
dispatch records, using a consistent PostgreSQL snapshot. No document contents,
emails, skills, application text, provider URLs or user IDs are displayed.
The schema check highlights *new*, unknown user/profile-owner tables so that
future features do not silently escape a planned purge.

## Known incomplete obligations

- No remote deletion API or provider-attested deletion receipts: ambiguous
  network sends may exist even if SmartPloy has no returned provider job ID.
  Interactive/manual ObumAI sends outside the durable ledger may also exist.
- No hard local purge or final erasure certificate. Requests remain quarantined
  until provider obligations, local cleanup ordering, re-registration/tombstone
  policy, backups, logs, OIDC state and retention obligations are independently
  reviewed.
- Worker status-refresh selection excludes disabled, identity-linked profiles
  but does not itself cancel remote provider activity. In-flight requests or
  edits started before disabling require additional audit.
- Account-specific remote job IDs and request IDs can be personal information;
  the operator-only internal listing requires secure restricted handling.
- No authenticated public deletion endpoint and no permission inferred from
  a caller-provided user ID, email or web form.
- No automatic process or runtime environment toggle enables this workflow.

**Production authority:** none. This branch is a draft, synthetic/isolated CI
evidence only. Full self-service deletion, remote cleanup and a formal retention
policy require product/legal/security review and explicit owner approval.
