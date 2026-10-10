# SmartPloy first installation on obum-core-01

Use this path when the host has **no SmartPloy checkout, private environment, or running containers**.
It is not a recovery tool for existing database data. The bootstrap deliberately refuses to mint a
new PostgreSQL password when the `smartploy-postgres` volume, a prior deployment marker, or a
SmartPloy dump already exists.

## Phase 1 — provision code and private environment

Run on `obum-core-01` as a sudo-authorized operator:

```bash
sudo mkdir -p /srv/obum/stacks
sudo git clone https://github.com/galapoto/smartploy.git /srv/obum/stacks/smartploy
cd /srv/obum/stacks/smartploy
sudo bash deploy/personal/scripts/bootstrap-first-host.sh
```

The script:

- creates `deploy/personal/env` with mode 600 using exclusive creation;
- generates a cryptographically random URL-safe PostgreSQL password without printing it;
- leaves ObumAI machine integration disabled until its authorized service identity exists;
- leaves Cloudflare Access issuer, audience and approved owner as **unusable placeholders**
  until the real dedicated Access application is configured;
- does not create containers, change any Caddy or cloudflared configuration,
  mutate other stacks, or alter Cloudflare DNS.

Edit the private file **on the host**:

```bash
sudoedit /srv/obum/stacks/smartploy/deploy/personal/env
```

Set exactly the reviewed values for `SMARTPLOY_ACCESS_ISSUER`,
`SMARTPLOY_ACCESS_AUDIENCE` and `SMARTPLOY_ACCESS_ALLOWED_EMAIL`.
Do not paste these values into a GitHub issue, logs, or a public chat.
Do not enable `OBUMAI_BASE_URL` until a valid least-privilege machine identity is ready.

## Phase 2 — preflight and initial deploy

```bash
cd /srv/obum/stacks/smartploy
sudo bash deploy/personal/scripts/preflight.sh
```

Only after this passes and the exact reviewed main SHA has been confirmed,
run the deployment gate:

```bash
sudo bash deploy/personal/scripts/deploy.sh main
```

The deploy gate builds only the SmartPloy Compose project, creates a private PostgreSQL
volume and a pre-deploy backup, runs its migrations, and checks the SmartPloy
localhost gateway at `127.0.0.1:8091/healthz`.
It does not modify the ObumAI Compose project or its database.

Confirm origin readiness without printing credential-bearing responses:

```bash
curl -sS --max-time 10 -H 'Host: smartploy.obumai.com' \
  -o /dev/null -w 'origin_health_http=%{http_code}\n' \
  http://127.0.0.1:8091/healthz
```

Do not continue to external routing unless origin health is HTTP 200.

## Phase 3 — inspect and configure existing Cloudflare ingress

The host currently runs both `caddy` and `cloudflared`, but prior operator
checks found neither :443 nor :8091 listening and no SmartPloy hostname in
`/etc/caddy/Caddyfile`. Do **not** assume that all Cloudflare requests actually
pass through host Caddy. Check the existing tunnel's ingress rules/public hostnames.

Two supported patterns (choose the one matching the existing deployment):

- **Tunnel ingress:** Cloudflare Tunnel public hostname `smartploy.obumai.com`
  directs to `http://127.0.0.1:8091`. Keep port 8091 loopback-only.
- **Approved host reverse proxy:** The established Caddy entry point routes this exact
  hostname to `127.0.0.1:8091`. Preserve other hostnames, network and TLS settings.

Do not add a new, conflicting Caddy listener to a running shared host.
Keep Cloudflare edge protection and the dedicated temporary Access policy while
Obum Identity remains uncommissioned.

After routing and identity are configured, run:

```bash
cd /srv/obum/stacks/smartploy
sudo bash deploy/personal/scripts/live-acceptance.sh
sudo bash deploy/personal/scripts/release-evidence.sh --online
```

The first-host bootstrap does not authorize external job application submission.
Do not deploy feature branches, switch authentication to OIDC, or disable
Cloudflare Access in response to a 502.
