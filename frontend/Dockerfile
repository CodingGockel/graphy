# Web image: builds the SvelteKit static SPA, then serves it with nginx and
# proxies /api to the backend. This container is the public entrypoint.

# ---- Stage 1: build the static SPA ----
FROM node:20-slim AS build

WORKDIR /app

# Install dependencies with the lockfile for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

# Build the static output (adapter-static -> build/).
COPY . .

# Optional: override the API base at build time (defaults to relative /api/v1,
# which works behind this image's nginx proxy).
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# ---- Stage 2: serve with nginx ----
FROM nginx:1.27-alpine

# Site config (static + /api proxy).
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Static SPA assets.
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80

# Use 127.0.0.1, not "localhost": inside the container localhost resolves to ::1
# (IPv6) first, but nginx only listens on IPv4 (`listen 80;`), so a localhost probe
# fails and the container is wrongly marked unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
