# Vyom UI image (S1.7). Build context is frontend/. Built by scripts/vyom-up.sh.
ARG NODE_IMAGE=node:26-alpine
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.29-alpine

FROM ${NODE_IMAGE} AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM ${NGINX_IMAGE}
# Serves the built UI and forwards /api to the API Service; nothing else leaves the pod.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
