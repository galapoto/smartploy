# Job-scoped ObumAI consent — privacy staging contract

Status: DRAFT SOURCE ONLY. No production unattended AI activation is authorized.

## What a user explicitly permits

A signed-in user selects one current job and checks an affirmative permission
statement in Settings. The backend binds the grant to:

- stable verified SmartPloy user ID (never the email address);
- that user's active profile ID;
- canonical job key and SHA-256 of the current application-relevant job snapshot;
- SHA-256 of currently approved CV/profile evidence;
- fixed processor ObumAI, draft-preparation purpose, unattended mode.

A user cannot supply alternate identities, processor names, recipients, custom
agent actions or employer-submission authority. The user must have approved
evidence, the job must be current, and the source must explicitly allow AI
forwarding. Merely connecting Ollama, setting job preferences or viewing a job
does NOT give consent. No automatic processing starts when a grant is saved.

## API (all private, authenticated)

    GET    /api/v1/ai-processing-consents
    GET    /api/v1/ai-processing-consents/events
    POST   /api/v1/ai-processing-consents
    DELETE /api/v1/ai-processing-consents/{consent_id}

The POST body is exactly:

    {"canonical_key":"reviewed-job-key","acknowledge_obumai_processing":true}

Missing/false/coerced consent is rejected. The existing identity middleware
handles session verification, same-origin mutation checks and the browser's
X-Smartploy-Expected-User-Id stale-session precondition. All successful private
API responses have no-store caching policy.

GET returns only the requesting verified account's permissions and history.
Unknown or wrong-owner revoke is a generic 404. Duplicate grants are idempotent.
Revocation is idempotent. A new version/event is recorded on regrant or changed
approved evidence or job content, without storing any raw CV or posting text
in the consent tables. Grant/revoke events are not actual processing receipts.

The Settings UI deliberately displays that saving permission is not a request
for AI inference or any employer action. Withdrawal stops future authorization
but cannot cancel remote tasks already running or delete previously shared data.

## Database / retention

Migration 016 adds one current/revoked row per (user_id, profile_id, job key)
and append-only consent events, with hashes, revisions and timestamps only.
It does not introduce new foreign keys that interfere with legacy test/owner
database truncation; account erasure must explicitly delete permission AND
audit rows under an approved retention and regulatory policy. Such an erasure
workflow is not implemented here.

The Postgres repository verifies the active identity/profile binding within
the transaction before granting permission. The read-only authorization method
also checks that the account is active, the profile binding is unchanged,
the record has not been revoked, and the exact job and evidence hashes match.

## Staged transaction-safe dispatch guard (not connected to a worker)

The PostgreSQL consent ledger now also offers an INTERNAL,
non-API `hold_authorized_dispatch(binding, job_key, job_hash, evidence_hash)`
context manager for one bounded outbound dispatch attempt. This method:

- verifies the active owner and exact profile in the database, holding row
  locks on the user and profile;
- locks only the matching live, nonrevoked consent revision using
  `SELECT ... FOR UPDATE`, serializing concurrent dispatchers and conflicting
  with withdrawal or regrant
  updates;
- raises on missing, revoked, disabled, wrong-owner or stale-snapshot consent;
- holds those locks until the protected block exits. If a revocation commits
  before lock acquisition, the send is refused. If a send owns the lock first,
  revocation waits and is only confirmed after the send completes.

Database timeouts and outages fail closed. No AI call occurs in this module.
Tests exercise actual PostgreSQL concurrent withdrawal versus held locks.
This guard **does not yet re-fetch source rights or evidence, send a model
request, provide a durable delivery receipt, or handle cancellation**.
A future caller must do all of those and send only the exact previously
authorized snapshot INSIDE the locked block. A long-lived transaction during
remote HTTP is an architecture tradeoff still requiring independent review.

For bounded internal *planning only*, `list_active_verified` returns
active, account-verified and nonrevoked grants, without email or CV data.
`smartploy.consented_worker_readiness.preview_consented_preparations(dsn)`
now re-fetches the live user/profile, current job, approved evidence, source
forwarding policy and scoring. It reports only aggregate counts for job missing,
source restricted, unqualified, changed snapshots, existing drafts or ready
cases. It does not create queues, register a worker task, call ObumAI or
authorize a send. Limit is bounded to 500 records.

Reading this list or obtaining a "ready" preview is NOT permission to send
anything. Fair cursor paging, safe retry/reservation, source checks under
the actual dispatch lock, and withdrawal at the send boundary remain release
blockers.

## Explicitly missing: safe multi-user worker dispatch

The existing unattended worker stays disabled and raises if the legacy global
operator flag is enabled in production. This PR does not start any reasoning
task, does not select consented accounts for background work, and does not
request employer applications.

A future worker must use tenant-scoped profile, application and preparation
repositories for every eligible user. It must re-fetch the job, re-evaluate
source rights and eligibility, rehash approved evidence and job content, check
revocable consent immediately before each dispatch/retry, and prevent
revoke-vs-dispatch races with durable transactional reservation semantics.
A missing consent record, stale snapshot, disabled user, wrong tenant or DB
outage must fail closed. Test same-email/different-subject, retries,
withdrawal, source changes and in-flight races before permitting production.

Source approvals, real human relevance evaluations, live second-account
browser verification and an owner-approved pinned backup-first OVH rollout
are independent release gates. Green synthetic CI does not satisfy them.

Related tracking: GitHub SmartPloy issue #139, source draft #137 and the
status-queue draft #140. Do not merge this stacked draft directly to main.
