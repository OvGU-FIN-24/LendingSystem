# React build
FROM node:24.21.0-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# No source maps in the production image (they would ship the full source)
ENV GENERATE_SOURCEMAP=false
# Serve the PDF.js worker from the same origin, matching the installed pdfjs-dist version
RUN cp node_modules/pdfjs-dist/build/pdf.worker.min.js public/ \
    && npm run build

# Static files and reverse proxy, unprivileged nginx (uid 101, port 8080)
FROM nginxinc/nginx-unprivileged:1.30.5-alpine

ENV NGINX_ENVSUBST_FILTER=TRUSTED_
ENV TRUSTED_PROXY_CIDR=127.0.0.1/32

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080
