# SP15e - verifiable reuse-first employer final action gate

18 October 2026. DRAFT SOURCE ONLY. No employer request, final browser
click, production deployment, applicant-facing approval/consume route or
verified provider receipt is created by this increment.

## First: existing code audited and reused

| Existing built product | Verified source blob | Concrete reuse and adaptation |
| --- | --- | --- |
| SmartPloy permanent employer claim | smartploy/employer_submit_claim_storage.py feeb3cee32927abd77883c8129bec1bf9a4fdf31 | Refactored its actual existing immutable PostgreSQL insert+read (~25 old lines) into reserve_employer_claim_locked, now shared by SP15a and SP15e. No second claim ledger |
| SmartPloy shared locked identity and document preflight | Same first-party SP15a source feeb3cee | Reused verified_employer_submit_preflight, existing account-erasure lock order, current job, documents, observed receipt and CRM deny gates |
| SmartPloy reviewed intent | employer_review_intent_storage.py 0e3cc79d0473961fc69662b6b149ab4a1b7b5052 | Reused existing 10-minute owner+job+CV PDF review under PostgreSQL FOR UPDATE, not a duplicate review store |
| SmartPloy deterministic packet and profile | browser_handoff.py 5543583af9359c37c91af14bd066de8788a7a5e0 | Reused approved contact mapping and UTF-8 field fingerprint, canonical Lever employer identity, CandidateProfile and ProfileFact |
| SmartPloy OIDC/CSRF owner authentication | api.py de8f5e95393008ee75739f32fb0bb7d2df1bf967 and oidc.py 015ca5df354979b090384b5aa6efc2a3f34e2cb6 | Reused signed_in_employer_review for READ-ONLY readiness, same-origin and tenant-ownership; no second login or writable grant API |
| SmartPloy SourcePolicy discovery terms | domain.py SourcePolicy.allows | Explicitly REJECTED as authorization to submit to employers. Acquisition approval does not grant employer automation rights |
| ObumAI Agent B preflight | obumellm/application/final_submit_preflight.py b5c5e99e008162f43efa09d05582856bcf05300e | Adapted deterministic field/document evidence separation, not code copied |
| ObumAI Agent D control plane | obumellm/platform/control_plane.py e6259a75b3bf4aecfb514e3b9747760a5a4b2770 | Adapted approved authority vs idempotent reservation vs uncertain outcome, not its in-memory state unsuitable for PostgreSQL two-device concurrency |

No third-party code imported, no new packages, parallel browser engine,
additional OAuth stack or paid workflow. No license circumvention.

## Second: only previously missing code created from scratch

1. New smartploy/employer_automation_rights.py and migration 021 policy
   table: exact employer/job permission requires explicit employer
   authorization or documented partner integration, evidence digests, two
   different operator reviewers, current audit and at most 90-day validity.
   Default DENY. No applicant, extension or operator HTTP rights-write route.
   Out-of-band evidence still requires independent human verification.
2. New smartploy/employer_final_action_gate.py and migration 021 final
   approvals table: a separate 90-second user-final-approval record bound to
   owner, reviewed CV/PDF, exact job and approved fields; NO bearer token.
   An internal consume method uses the existing SP15a atomic claim insert
   in the SAME transaction as changing the final approval state. One
   reserved_unverified marker, never an employer-received assertion.
3. Adapted existing account erasure inventory to include the new owner
   approval table. Adapted existing signed-in API and Application Studio
   to show a private, read-only employer-policy readiness indicator, never
   a click permission or user-accessible final grant issuance route.
4. Synthetic tests reuse the existing scoped PostgreSQL identity/owner/job
   fixture and verify default deny, two distinct rights reviewers, actual
   final user approval, revoked rights, stale contact facts, expiration,
   same-email separate accounts, eight competing consumes, quarantine
   inventory and no retry.

## Third: boundaries and progress

Before SP15e, SmartPloy had CV review and generic sticky claims, but no
separate employer-specific rights attestation, bounded fresh final user
approval or same-transaction final-approval consumption with a cross-device
sticky claim.

After SP15e, these internal P0 controls can be exercised in synthetic
PostgreSQL tests without redesigning the runtime or activating an unsafe
browser click. This is real core engineering, NOT a completed automated
employer application.

Limitations: actual employer terms were NOT verified during this change.
No production rights entry is added. The 90-second approval is not a
browser grant. The internal consume method has no network/API route and
does not click Submit. Real user OIDC-to-Chrome pairing, final DOM snapshot,
one-use immediate claim redemption, two-browser authenticated E2E, native
ObumDelivery with RED negative control, employer receipt and OVH owner
release must be independently verified. No self-reported or browser-observed
result counts as independently confirmed employer acceptance.

RELEASE HOLD: no main merge, no employer traffic, no OVH deployment.
Exact-source CI details are recorded only after the actual new commit runs.
