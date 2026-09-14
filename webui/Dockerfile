FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine@sha256:72ba65eb42c10344912a84ff42408db7d34f2feb642204570ab8fc5ffd29f1d3
RUN apk add --no-cache --upgrade libuuid \
    && sed -i '/^user /d' /etc/nginx/nginx.conf \
    && sed -i 's|pid        /run/nginx.pid;|pid        /tmp/nginx.pid;|' /etc/nginx/nginx.conf \
    && chown -R 101:101 /usr/share/nginx/html /var/cache/nginx /var/log/nginx
COPY --from=builder --chown=101:101 /app/dist /usr/share/nginx/html
COPY --from=builder --chown=101:101 /app/nginx.conf /etc/nginx/conf.d/default.conf

USER 101:101
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
