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
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
