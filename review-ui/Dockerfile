FROM node:20-alpine AS build
WORKDIR /app
# `npm ci` sobre el lockfile versionado: sin esto, `npm install` resolvía los rangos
# (`react: ^18.3.1`) en cada build, y dos builds del mismo commit podían dar bundles distintos.
COPY package.json package-lock.json ./
# Playwright es devDependency (tests de UI) y su instalación baja navegadores: acá no se usan,
# y descargarlos costaría cientos de MB en cada build de la imagen.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# Plantilla, no config fija: el gateway se resuelve por env en el arranque. El default deja el
# `docker compose` funcionando sin configurar nada, porque ahí el servicio se llama así.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV GATEWAY_ORIGIN=http://api-gateway:8000
# El entrypoint solo exporta NGINX_LOCAL_RESOLVERS (leído de /etc/resolv.conf) si este flag
# está puesto; sin él, la plantilla se renderiza con el `${NGINX_LOCAL_RESOLVERS}` literal y
# nginx muere con "host not found in resolver".
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
