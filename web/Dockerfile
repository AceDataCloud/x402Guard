# Build the static Dapp; the resulting `dist/` is served by an nginx
# alpine image. Production sits behind Caddy / cloudfront / whatever —
# the nginx layer just hosts assets and routes /api + /mcp to the
# backend service via the `BACKEND_URL` build arg.

FROM node:20-alpine AS build
WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build


FROM nginx:1.27-alpine AS runtime

# Inject the runtime nginx config that proxies /api + /mcp to the
# backend service named `api` on the same docker network / k8s service.
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost/index.html >/dev/null || exit 1
