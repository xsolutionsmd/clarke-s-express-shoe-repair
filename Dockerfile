# Native build tools run on the builder platform; the output is static on both Oracle architectures.
FROM --platform=$BUILDPLATFORM node:22-alpine AS dependencies
WORKDIR /workspace
COPY app/package.json app/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM dependencies AS development
ARG APP_REVISION=unknown
ARG REVISION=${APP_REVISION}
ARG APP_SOURCE_URL=unknown
ENV APP_REVISION=${REVISION}
LABEL org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.source="${APP_SOURCE_URL}"
COPY app/ ./
COPY runtime/vite.config.mjs /opt/runtime/vite.config.mjs
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:8080/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
# The named node_modules volume hides Windows host dependencies. Refresh it on lockfile changes.
CMD ["sh", "-c", "npm ci --no-audit --no-fund && npm run dev -- --config /opt/runtime/vite.config.mjs"]

FROM dependencies AS test
COPY app/ ./
RUN npm run check
ARG APP_REVISION=unknown
ARG REVISION=${APP_REVISION}
RUN node -e "require('node:fs').writeFileSync('dist/version.json', JSON.stringify({revision: process.env.REVISION}) + '\\n')"
CMD ["npm", "run", "check"]

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
ARG APP_REVISION=unknown
ARG REVISION=${APP_REVISION}
ARG APP_SOURCE_URL=unknown
LABEL org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.source="${APP_SOURCE_URL}"
COPY runtime/nginx.conf /etc/nginx/nginx.conf
COPY --from=test --chown=10001:10001 /workspace/dist/ /srv/site/
USER 10001:10001
RUN nginx -t
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/health >/dev/null || exit 1
# Bypass the base image's configuration-mutating entrypoint; nginx only writes to /tmp.
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
