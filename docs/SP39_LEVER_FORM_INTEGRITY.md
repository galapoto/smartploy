# SP39 — Freeze reviewed employer form bindings across asynchronous CV checks

**Date:** 25 October 2026  
**Plan:** SP21 P0-C end-to-end authorized browser submission; Agentic SmartPloy Gate 1 single reviewed employer action.  
**Source baseline:** SP38 `main@0b2cfee0aa8280861f015510a6961de608208378`.  
**Status:** source implementation proposed for CI; native ObumDelivery and OVH rollout are independent.

## Core defect closed

The original SP26/SP29 Lever-only extension checks the reviewed PDF digest, approved
name/email/cover letter, resolved required fields, CAPTCHA and one-click marker before
a final click. The CV read and SHA-256 digest are asynchronous. Before SP39, an
employer form could change a *non-required answer*, hidden field, consent checkbox
or final form/button destination during this await without failing the second
pre-click review. Those represent materially different application data or
destination from what the applicant saw.

## Reuse-first implementation

**Reused:** original one-use reviewed Lever adapter
`browser-companion/page-final-submit.mjs`, original approved exact job URL, CV hash
and non-retry claim, live same-form element/required-field checks, original Node
fake-employer regression harness, and Finnish/Swedish label support. No new agent
runtime, provider connector, browser permissions, database tables or dependencies.

**Only new:** a compact synchronous snapshot of control values, required/disabled/
read-only state, optional checkbox values, identity/label/placeholder metadata,
select options, form submit destination/method and button overrides. Capture after
the first validity check and before CV hashing. Compare each binding after
hashing, in the existing synchronous final pre-click gate. Any changed
binding yields `employer_form_changed` without clicking or retrying.

The existing atomic server claim and browser attempt marker still govern the
one-time final click. A browser click is NOT a provider acknowledgment.

## Core function and negative controls

Node regression scenarios mutate a real form input object *during the
asynchronous PDF read*. All must produce zero clicks:

- Previously reviewed optional text answer replaced.
- Optional checkbox modified.
- Hidden employer field/token changed.
- Employer question label or name changed its meaning.
- Form action or final button override pointed to another destination.
- Previously covered changed email, name, letter, CV, duplicate button, late
  CAPTCHA, added input, new attachment, changed required field and re-try marker.

Positive controls retain exactly one click on a stable synthetic Lever form,
including native Finnish `Lähetä hakemus` and Swedish `Skicka ansökan`
labels, with a second click blocked. No external employer, recipient,
account or private CV is used by synthetic CI.

## Limitations / next core gates

This integrity guard **does not** turn the general web into a consented ATS
submitter. Browser final submit remains private operator-default **OFF**.
Production requires rights-approved exact employer job, owner review, a
short-lived server reservation, native Woodpecker exact-SHA qualification,
guarded OVH rollout, live authenticated test and verified provider receipt.
Many non-Lever ATS forms remain unsupported and require the applicant.

The next priorities are a real signed-in OVH browser acceptance, in-app
Agent Zero wake receipt, and an individually authorized additional employer
adapter/acknowledgment. Continue collecting direct Finland jobs separately
from claims of actually submitting applications.
