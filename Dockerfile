FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS frontend-deps
WORKDIR /workspace
COPY app/package.json app/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM frontend-deps AS frontend
COPY app/ ./
RUN npm run check

FROM python:3.12-slim-bookworm AS backend-deps
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data MALLOC_ARENA_MAX=2
RUN apt-get update && apt-get install -y --no-install-recommends wget libseccomp2 liblcms2-2 tzdata && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --no-create-home clarke && mkdir /data && chown 10001:10001 /data
WORKDIR /workspace
COPY app/requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /opt/requirements.txt

FROM backend-deps AS backend-base
COPY app/server.py app/wsgi.py app/gunicorn.conf.py ./
COPY app/clarke/ ./clarke/
COPY app/migrations/ ./migrations/

FROM backend-base AS backend-test
COPY app/requirements-test.txt /opt/requirements-test.txt
RUN pip install --no-cache-dir -r /opt/requirements-test.txt
COPY app/tests/ ./tests/
RUN python tests/make_heic.py
USER 10001:10001
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]

FROM backend-test AS test
COPY --from=frontend /workspace/dist/ ./dist/
RUN python -m pytest -q -p no:cacheprovider tests

FROM backend-base AS development
COPY --from=frontend-deps /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-deps /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
RUN mkdir -p /workspace/node_modules && chown -R 10001:10001 /workspace/node_modules
ENV npm_config_cache=/tmp/clarke-npm
COPY runtime/development.sh /opt/runtime/development.sh
ARG APP_REVISION=unknown
ARG APP_SOURCE_URL=unknown
ENV APP_REVISION=${APP_REVISION}
LABEL org.opencontainers.image.revision="${APP_REVISION}" org.opencontainers.image.source="${APP_SOURCE_URL}"
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=5 CMD wget -qO- http://127.0.0.1:8080/health >/dev/null || exit 1
CMD ["sh", "/opt/runtime/development.sh"]

FROM backend-base AS backend-runtime
ARG APP_REVISION=unknown
ARG REVISION=${APP_REVISION}
ARG APP_SOURCE_URL=unknown
LABEL org.opencontainers.image.revision="${REVISION}" org.opencontainers.image.source="${APP_SOURCE_URL}"
RUN printf '%s' "${REVISION}" > /workspace/revision.txt
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 CMD wget -qO- http://127.0.0.1:8080/health >/dev/null || exit 1
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]

FROM backend-test AS api-test
COPY tests/e2e/seed_sessions.py tests/e2e/api_probe.py /probe/
WORKDIR /probe
ENV PYTHONPATH=/workspace
CMD ["python", "api_probe.py", "create"]

FROM backend-deps AS e2e
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
COPY tests/e2e/requirements.txt /opt/e2e-requirements.txt
RUN pip install --no-cache-dir -r /opt/e2e-requirements.txt && playwright install --with-deps chromium
COPY --from=backend-test /opt/test-fixtures/ /opt/test-fixtures/
COPY tests/e2e/ /e2e/
WORKDIR /e2e
ENV PYTHONPATH=/workspace
USER 10001:10001
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short", "/e2e"]

# Keep the final/default target identical to the published application image.
FROM backend-runtime AS runtime
COPY --from=frontend /workspace/dist/ ./dist/
