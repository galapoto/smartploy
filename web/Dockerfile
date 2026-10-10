FROM node:22-alpine AS build

WORKDIR /app
COPY web/package.json ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM caddy:2.10.2-alpine
COPY deploy/personal/web.Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 8080
