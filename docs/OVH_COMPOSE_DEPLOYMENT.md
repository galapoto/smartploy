# SmartPloy production stack on obum-core-01

## Host layout

Target repository:

`/srv/obum/stacks/smartploy`

Persistent host paths:

- deployment state: `/srv/obum/data/smartploy/deploy-state`
- backups: `/srv/obum/backups/smartploy`

The Compose stack owns its PostgreSQL volume.

## Runtime topology

```text
Cloudflare
    |
    v
host/shared ingress (Caddy)
    |
    v
127.0.0.1:8091
    |
    v
SmartPloy web gateway (Caddy container)
    |                       |
    | static React          | /api + /healthz
    v                       v
  web/dist              SmartPloy API
                            |
                   +--------+--------+
                   |                 |
               PostgreSQL         ObumAI /
                                  job sources

Continuous worker -> PostgreSQL + approved external sources + bounded ObumAI preparation
```

Only the web gateway is published to the host, and it binds to loopback.

PostgreSQL, API and worker have no host port.

## Initial host setup

Clone the repository to:

~~~bash
sudo install -d /srv/obum/stacks
cd /srv/obum/stacks
git clone https://github.com/galapoto/smartploy.git smartploy
cd smartploy
cp deploy/personal/env.example deploy/personal/env
chmod 600 deploy/personal/env
~~~

Fill `deploy/personal/env` with:
- URL-safe PostgreSQL password;
- SmartPloy Cloudflare Access issuer/audience/approved owner email;
- reviewed ObumAI machine-auth configuration;
- enabled source credentials/configuration.

Do not commit that file.

## Shared host Caddy

The host ingress only needs:

~~~caddy
smartploy.obumai.com {
    reverse_proxy 127.0.0.1:8091
}
~~~

A copy is stored at `deploy/personal/Caddyfile.host.example`.

Cloudflare remains the public DNS/TLS/Access edge. The SmartPloy API independently verifies the Access
application JWT.

## Deploy

~~~bash
cd /srv/obum/stacks/smartploy
bash deploy/personal/scripts/deploy.sh main
~~~

The gate:
1. acquires a host deployment lock;
2. checks out the exact requested Git ref;
3. validates committed production policy;
4. validates Compose;
5. builds API/web images;
6. starts PostgreSQL;
7. creates a pre-deploy PostgreSQL dump;
8. runs migrations once;
9. starts API, worker and web;
10. validates health through `127.0.0.1:8091` using the production Host header;
11. confirms all four services are running;
12. records the exact deployed SHA.

A failed health check does not overwrite the last deployed SHA.

## Backups

Manual backup:

~~~bash
bash deploy/personal/scripts/backup.sh
~~~

Backups:
- use PostgreSQL custom dump format;
- are created with private permissions;
- receive SHA256 sidecar files;
- are stored in `/srv/obum/backups/smartploy` by default;
- retain the newest seven dumps by default.

## Product authority

Deployment does not authorize external job application submission.

The continuous worker may discover/rank jobs and prepare evidence-bound drafts through approved ObumAI
boundaries. Final application submission remains outside this stack's current authority.
