# SmartPloy HTTP 502 origin recovery

## Impact and boundary

A Cloudflare-branded HTTP 502 for `smartploy.obumai.com` means the public edge was reached,
but an origin server or backend route failed. This does **not** justify disabling Cloudflare
Access, changing authentication mode, changing DNS to expose the origin directly, or
rebuilding the entire ObumAI ecosystem.

Approved current deployment topology:

```
Cloudflare edge -> OVH host Caddy (:443)
               -> 127.0.0.1:8091
               -> SmartPloy web (container :8080)
               -> SmartPloy API (:8090, private Docker network)
               -> PostgreSQL (private Docker network)
```

The new `deploy/personal/scripts/diagnose-origin-502.sh` is read-only.
It only prints booleans, port numbers, service state and local HTTP status codes;
it does not output production secrets, database connection strings or HTTP bodies.

## Diagnosis on the OVH host

Run as an operator authorized to read Docker status:

```bash
cd /srv/obum/stacks/smartploy
bash deploy/personal/scripts/diagnose-origin-502.sh
```

Check the result:

1. `production_env=missing_or_symlink`: bootstrap the private production
   environment from `deploy/personal/env.example`, with mode 600 and
   reviewed secret values. Do not paste secrets into issues or chat.
2. `docker=unavailable_or_permission_denied`: check Docker daemon and operator privileges.
3. `service_postgres=not_running_or_unavailable`: investigate database availability and volume,
   avoiding destructive `down -v` or new database initialization.
4. `service_api=not_running_or_unavailable`: check API startup, schema migrations and health.
5. `service_web=not_running_or_unavailable`: check web gateway and API health dependency.
6. `loopback_health_http` not 200: fix SmartPloy Compose stack first.
7. `loopback_health_http=200` but host ingress fails: inspect Caddy :443 host
   route for the exact hostname to `127.0.0.1:8091`.
8. Local loopback and host ingress healthy but public 502: examine
   Cloudflare proxied DNS origin target, routing, allowed origin connections,
   Tunnel ingress (if used), TLS Full (strict), and Cloudflare request logs.

Note: the host-local HTTPS probe uses normal certificate validation. If an
origin is configured with a private Cloudflare Origin CA certificate, this probe
may return HTTP 000 even when Caddy is active; investigate the certificate trust
chain using approved host tools rather than weakening public TLS.

## Non-destructive recovery

Only after identifying the failed layer and checking real environment readiness:

```bash
cd /srv/obum/stacks/smartploy
bash deploy/personal/scripts/preflight.sh
```

For an **initial** deployment or reviewed repair, follow `docs/OVH_COMPOSE_DEPLOYMENT.md`
and `deploy/personal/scripts/deploy.sh main`. That script performs builds,
migration and a database backup, so it must not be run merely as an exploratory
diagnostic. Do not bypass any failures with `--insecure` or disable
Cloudflare Access to make HTTP 200 appear.

## Post-repair gate

```bash
bash deploy/personal/scripts/live-acceptance.sh
bash deploy/personal/scripts/release-evidence.sh --online
```

Record deployed SHA, host ingress local health, Cloudflare public protection,
and evidence hashes. Do not close go-live issue #57 while live acceptance
fails. Keep the production auth mode `cloudflare` until separate Obum Identity
OIDC migration conditions are met in issue #64.
