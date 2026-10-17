FROM node:22-alpine AS build

WORKDIR /app
RUN npm install --global npm@10.9.2 --no-audit --no-fund
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM caddy:2.10.2-alpine
COPY deploy/personal/web.Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 8080
