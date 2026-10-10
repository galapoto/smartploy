# Application CRM and audit ledger

Smartploy keeps preparation and application submission as different concepts.

A completed CV/cover-letter package is **ready for review**. It is not an application submission.

## Preparation-driven states

- `preparing`
- `ready_for_review`
- `needs_review`
- `preparation_blocked`

Only preparation-package state can drive these values.

## Externally evidenced states

Reserved for later verified workflows:

- `submitted`
- `acknowledged`
- `recruiter_contact`
- `assessment`
- `interview`
- `offer`
- `rejected`
- `withdrawn`

Preparation synchronization never creates one of these states and cannot regress an externally evidenced state.

## Events

Every package-state synchronization appends an idempotent event. The event ID binds:

- application;
- event type;
- source type;
- package/status source ID;
- target state.

The current record is a projection over this audit history.

## Summary

`GET /api/v1/applications/summary` separates:

- pipeline state counts;
- items awaiting review;
- items still preparing;
- records that have actually been submitted.

`has_been_submitted` depends on `submitted_at`, not on preparation state.

Future ObumAI submission confirmation, Gmail outcomes and interview events will append verified events through
this ledger rather than rewriting history.
