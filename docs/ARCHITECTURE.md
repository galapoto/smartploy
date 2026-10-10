# Smartploy architecture

## Decision

Smartploy is a standalone product. ObumAI is a dependency, not a package boundary.

```text
Finnish job sources
      |
      v
+-----------------------------+
| Smartploy source adapters   |
| policy + health + evidence  |
+-----------------------------+
      |
      v
+-----------------------------+
| Smartploy job intelligence  |
| normalize / dedupe / fresh  |
| hard filters / Fit/Priority |
+-----------------------------+
      |
      +-------> Smartploy PostgreSQL (next slice)
      |
      v
+-----------------------------+
| Smartploy application layer |
| profile/CV versions / CRM   |
+-----------------------------+
      |
      | bounded reasoning request
      v
+-----------------------------+
| ObumAI durable job API      |
| reasoning / drafting        |
| controlled execution later  |
+-----------------------------+
```

## Ownership boundary

Smartploy owns source acquisition, source policy, canonical job identity, job-state persistence,
ranking, user profile/application state and the product UI.

ObumAI owns reusable reasoning/execution capabilities and consequential-action controls. Smartploy
must not import `obumellm`, access ObumAI's database, or depend on ObumAI being available for basic
job discovery and browsing.

## Failure behavior

- Source connector failure: source health becomes degraded; existing Smartploy data remains available.
- ObumAI unavailable: jobs and scores remain available; AI preparation requests return unavailable/retryable.
- Job closes: reasoning/preparation handoff is blocked for new work.
- Untrusted posting content: stored as data only; never interpreted as system/tool authority.
- No source or AI response can authorize upload/submission.

## Persistence

The bootstrap uses an in-memory domain repository only to establish interfaces. PostgreSQL is the
next storage slice. Smartploy's database will be independent of ObumAI's durable-agent database.

## Deployment

Smartploy should run as its own service/container and may share the same OVH/Cloudflare platform
primitives as ObumAI. Sharing infrastructure does not mean sharing runtime state or database schemas.
