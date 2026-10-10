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
SMARTPLOY_PUBLIC_ORIGIN=https://smartploy.obumai.com
SMARTPLOY_ALLOWED_HOSTS=smartploy.obumai.com

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
