# ── Build stage ───────────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app

# Install deps first for layer caching
COPY package*.json ./
RUN npm ci

# API base URL must be baked at build time (Vite inlines VITE_* at build).
# Override in docker-compose / Dokploy build args per environment.
ARG VITE_API_URL=http://localhost:8000/api
ARG VITE_WS_URL=ws://localhost:8000/ws
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL

COPY . .
RUN npm run build

# ── Serve stage ───────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine
RUN apk add --no-cache curl

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# Healthcheck — Dokploy/Traefik can probe this
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1/healthz || exit 1
