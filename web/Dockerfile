FROM node:22-alpine AS build

# Build-only Python stdlib creates a reproducible first-party Chrome extension
# ZIP from exactly the same reviewed sources as the API/Node/Chromium tests.
# Neither Python nor extension sources are installed in the final Caddy image.
RUN apk add --no-cache python3
WORKDIR /workspace/web
RUN npm install --global npm@10.9.2 --no-audit --no-fund
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
COPY browser-companion/ ../browser-companion/
RUN npm run build

FROM caddy:2.10.2-alpine
COPY deploy/personal/web.Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 8080
