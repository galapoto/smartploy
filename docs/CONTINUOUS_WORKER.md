# Continuous Smartploy worker

## Why it exists

Smartploy source adapters are deterministic one-poll components. The continuous worker turns those
components into an always-on system without changing their source-specific safety rules.

A source is searched continuously because its task becomes due repeatedly in PostgreSQL. "Daily" should
describe an optional user digest, not discovery cadence.

## Persistent scheduler

Migration 006 creates smartploy_worker_tasks.

Each row records:

- task identity and kind;
- enabled state;
- cadence;
- next run time;
- lease owner and lease expiry;
- last start/completion;
- last result;
- consecutive failure count;
- bounded error text;
- non-secret task metadata.

Workers claim due rows with PostgreSQL row locking and SKIP LOCKED. The claim also writes a lease.
A second worker cannot claim that task until the lease expires.

If a process crashes, the expired lease is reclaimable. If a task completes, the lease is cleared.

## Task registration

At worker startup, Smartploy derives tasks from current configuration. Each cycle synchronizes those task definitions with PostgreSQL. Restart the worker after changing source/environment configuration.

Source tasks:

- source:kuntarekry only when KUNTAREKRY_FEED_URL exists;
- source:job-market-finland only when JOBMARKET_FINLAND_API_ENABLED=true and its settings validate;
- one source task for every configured SmartRecruiters/Lever tenant.

When OBUMAI_BASE_URL is configured, status refreshes are registered for existing
remote preparation jobs. The legacy application:prepare-eligible task is OFF by
default and is rejected at startup in production, even if the operator turns on
SMARTPLOY_WORKER_AUTO_PREPARE_ENABLED. It is available only in explicit test and
development fixtures; this global switch is **not per-user consent**.

Refresh selection filters to queued, running or blocked records with an assigned
ObumAI job ID *before* applying the batch limit. The least recently updated
records go first; this avoids completed history crowding out unfinished work and
rotates polling fairly across active jobs. Migration 015 provides a partial index.
It never starts a new ObumAI inference request.

Tasks that were previously registered but are no longer configured are disabled.

## Default cadence

- Job Market Finland: 300 seconds;
- Kuntarekry: 600 seconds;
- public ATS tenant: 600 seconds;
- prepare eligible applications: 120 seconds;
- refresh active ObumAI preparation jobs: 60 seconds.

All values are configurable with SMARTPLOY_WORKER_* environment variables.

## Failure backoff

Healthy/degraded completion schedules the normal cadence.

A failed task increases its own consecutive failure count and uses exponential backoff:

~~~text
delay = min(max_backoff, cadence * 2^consecutive_failures)
~~~

The default maximum is 3600 seconds.

Other due tasks still run in the same worker cycle.

## Commands

Apply migrations first:

~~~bash
export SMARTPLOY_DATABASE_URL='postgresql://...'
python scripts/migrate.py
~~~

Run one deterministic scheduler cycle:

~~~bash
python scripts/source_worker.py --once
~~~

Run continuously:

~~~bash
python scripts/source_worker.py
~~~

Each cycle writes a compact JSON result to stdout.

## Graceful stop

SIGTERM and SIGINT set the worker stop event. A continuous worker exits after the current task/cycle
boundary instead of starting another cycle.

The default task lease is 900 seconds so normal bounded HTTP source polls have room to finish. If a task
can legitimately exceed that, increase SMARTPLOY_WORKER_LEASE_SECONDS rather than running overlapping
workers for the same source.

## OVH / Ubuntu systemd

An example unit is included at:

~~~text
deploy/systemd/smartploy-source-worker.service.example
~~~

Suggested installation:

~~~bash
sudo useradd --system --home /srv/smartploy --shell /usr/sbin/nologin smartploy
sudo install -d -o smartploy -g smartploy /srv/smartploy
sudo install -d -m 0750 /etc/smartploy
sudo install -m 0644 deploy/systemd/smartploy-source-worker.service.example \
  /etc/systemd/system/smartploy-source-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now smartploy-source-worker
~~~

Store runtime configuration/secrets only in:

~~~text
/etc/smartploy/smartploy.env
~~~

The unit file contains no source credentials or ObumAI headers.

## Safety boundary

The continuous worker does not broaden authority.

It can:

- run configured read-only source retrieval;
- normalize/deduplicate/rank jobs;
- retire jobs according to each adapter's verified lifecycle rules;
- refresh already-submitted draft jobs;
- queue evidence-backed drafts only in explicit synthetic test/development
  environments with the legacy opt-in flag. Production unattended preparation
  remains disabled until user-scoped, revocable consent is enforced.

It cannot:

- bypass source terms;
- bypass CAPTCHA/MFA;
- upload documents;
- submit an application;
- send an employer message;
- claim that preparation equals submission.

Those external actions remain outside this worker.
