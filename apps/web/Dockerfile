# syntax=docker/dockerfile:1

FROM node:22-bookworm AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build -- --configuration production \
  && test -d dist/web/browser

FROM nginxinc/nginx-unprivileged:1.27-alpine AS web

USER root
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Stub upstream name for `nginx -t` at image build; at run Compose DNS resolves `api`.
RUN printf '127.0.0.1 api\n' >> /etc/hosts \
  && nginx -t \
  && rm -f /tmp/nginx.pid
# Must match angular.json build.options.outputPath + browser subdir
COPY --from=build /app/dist/web/browser /usr/share/nginx/html
RUN chown -R nginx:nginx /usr/share/nginx/html
USER nginx

EXPOSE 4200

CMD ["nginx", "-g", "daemon off;"]
