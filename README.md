# Clarke's Express Shoe Repair

The public-safe company KB and independent deployment infrastructure. Current runtime
is the noindex scaffold placeholder; the functional repair application is not built.
Read `AGENTS.md`, `kb/HANDOFF.md`, `kb/features.md`, and `docs/ORACLE_DEPLOYMENT.md`.

Branches `main`, `derek-dev`, and `abdul-dev` each publish only their own Oracle stack.
Production changes require an authorized, checked PR into main. Each environment has
independent data, runtime secrets, OAuth client, image package, updater and backup.

Run `python scripts/app.py check` for the placeholder container. Linux CI additionally
runs the updater recovery harness and complete-state backup tests. Local development
uses `app.ps1`/`app.sh`; stateful updates quiesce the local service and copy its whole
`/data` to ignored `.runtime/backups` before replacement. Preserve those keys and
encrypted-token data; do not put `.runtime` or runtime.env into Git.

The next build stage supplies the API contract and application against the feature
spec. Google/Gmail login and delivery acceptance require that backend. Infrastructure
verification does not mark any functional feature acceptance row as passed.
