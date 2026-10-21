# Built from the repository root (see docker-compose.yml): stage 1 builds the web app,
# stage 2 serves it. The result has no Node.js in it and needs no network at runtime.
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/security-headers.conf nginx/proxy-api.conf /etc/nginx/snippets/
COPY --from=web /web/dist/ /usr/share/nginx/html/
