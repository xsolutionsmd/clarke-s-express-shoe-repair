FROM node:22.22.0-bookworm-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94
ENV DO_NOT_TRACK=1 GRAFT_NO_SEED=1 GRAFT_NO_GITIGNORE=1 GRAFT_NO_IGNORE=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/graft
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
ENTRYPOINT ["node", "/opt/graft/node_modules/@nanonets/graft/dist/cli.js"]
