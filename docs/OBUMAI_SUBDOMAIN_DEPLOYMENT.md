# SmartPloy on smartploy.obumai.com

SmartPloy is a first-class ObumAI product while remaining independently deployed.

## Production URL

https://smartploy.obumai.com

The browser uses same-origin requests:
- / -> React/Vite build
- /api/* -> SmartPloy FastAPI
- /healthz -> SmartPloy FastAPI

No broad cross-origin CORS is required.

## OVH layout

/srv/smartploy
- Python virtual environment
- SmartPloy source
- web/dist production frontend

/etc/smartploy/smartploy.env
- runtime configuration and secrets

Nginx is the public ingress. Uvicorn listens only on 127.0.0.1:8090.

## Required production environment

SMARTPLOY_HOST=127.0.0.1
SMARTPLOY_PORT=8090
SMARTPLOY_ENVIRONMENT=production
SMARTPLOY_PUBLIC_ORIGIN=https://smartploy.obumai.com
SMARTPLOY_ALLOWED_HOSTS=smartploy.obumai.com
SMARTPLOY_ACCESS_ENABLED=true
SMARTPLOY_ACCESS_ISSUER=https://<your-team>.cloudflareaccess.com
SMARTPLOY_ACCESS_AUDIENCE=<smartploy-access-application-aud>
SMARTPLOY_ACCESS_ALLOWED_EMAIL=<approved-owner-email>

Also configure SMARTPLOY_DATABASE_URL and any source/ObumAI credentials in the external environment file.

Do not store credentials in Nginx or systemd unit files.

## Build and deploy

~~~bash
cd /srv/smartploy
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python scripts/migrate.py

cd web
npm ci
npm run build
~~~

Install the service examples:

~~~bash
sudo install -m 0644 deploy/systemd/smartploy-api.service.example   /etc/systemd/system/smartploy-api.service
sudo install -m 0644 deploy/systemd/smartploy-source-worker.service.example   /etc/systemd/system/smartploy-source-worker.service
sudo install -m 0644 deploy/nginx/smartploy.obumai.com.conf.example   /etc/nginx/sites-available/smartploy.obumai.com
sudo ln -s /etc/nginx/sites-available/smartploy.obumai.com   /etc/nginx/sites-enabled/smartploy.obumai.com
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now smartploy-api smartploy-source-worker
sudo systemctl reload nginx
~~~

## Cloudflare

Create DNS for smartploy.obumai.com to the approved OVH ingress and keep TLS/WAF at the Cloudflare edge according to the wider migration plan.

Application authorization remains a SmartPloy/ObumAI identity concern; DNS/Cloudflare routing must not be treated as application authentication.

## Security boundary

- exact host allowlist in SmartPloy;
- HTTPS public origin;
- no wildcard CORS;
- no shared parent-domain application cookie;
- CSP frame-ancestors 'none';
- same-origin browser API;
- no application-submit authority is introduced by deployment.

## ObumAI launcher

ObumAI should link directly to https://smartploy.obumai.com/ from its generic Tools registry.

The launcher does not proxy SmartPloy data and does not collapse databases or service ownership.


## Cloudflare Access identity boundary

SmartPloy follows the same Access trust pattern used by the current protected ObumAI workspace, but it
verifies its own token and uses its own application audience.

Create/provision a Cloudflare Access application for `smartploy.obumai.com`. Configure its issuer and
audience in the SmartPloy environment file.

Cloudflare sends the signed application assertion in:

`Cf-Access-Jwt-Assertion`

Nginx forwards that assertion to the localhost SmartPloy API. FastAPI independently verifies:
- fixed RS256;
- Cloudflare JWKS signature;
- exact issuer;
- exact SmartPloy audience;
- exp/iat/iss/aud/sub/email/type claims;
- `type=app`;
- exact configured owner email.

The API does not trust an unverified email header.

`/healthz` is deliberately exempt so the origin can be monitored. All other API routes require Access
when enabled.

### Single-owner limitation

SmartPloy currently has one profile/application data domain. Therefore production Access accepts exactly
one configured owner email. Do not add additional users to the application until SmartPloy storage is
tenant-scoped by authenticated principal.

This restriction is intentional: successful authentication alone must not expose one user's CV, job or
application state to another authenticated account.

### Relationship with ObumAI

Opening SmartPloy from ObumAI can reuse the browser's existing Cloudflare identity/session, so the user
may not need to enter credentials again. SmartPloy still receives and verifies a token for the SmartPloy
Access application and does not accept a generic ObumAI chat token as application authority.

No JWT is placed in the navigation URL or forwarded to ObumAI.


## Obum Identity application authentication

The customer-facing target is application-owned authentication through `auth.obumai.com`, not a
Cloudflare Access login page.

SmartPloy OIDC variables:

~~~text
SMARTPLOY_AUTH_MODE=hybrid
SMARTPLOY_OIDC_ISSUER=https://auth.obumai.com
SMARTPLOY_OIDC_CLIENT_ID=<registered-smartploy-client-id>
SMARTPLOY_OIDC_REDIRECT_URI=https://smartploy.obumai.com/auth/callback
SMARTPLOY_OIDC_POST_LOGOUT_REDIRECT_URI=https://smartploy.obumai.com/auth/logged-out
SMARTPLOY_OIDC_SCOPE=openid profile email
SMARTPLOY_SESSION_TTL_SECONDS=43200
SMARTPLOY_OIDC_STATE_TTL_SECONDS=600
~~~

OIDC variables belong only in the API service environment. They must not be injected into worker,
web or PostgreSQL containers.

The committed production policy intentionally remains `SMARTPLOY_AUTH_MODE=cloudflare` until
Obum Identity is deployed and the hybrid acceptance gate is ready.
