# Clarke's Express Shoe Repair

The public-safe company KB, functional repair application and independent deployment infrastructure.
The application supports photo requests, private repair status, estimates, staff tickets,
and location hours/notices. The first functional release is undergoing final verification;
the live environments still serve the noindex scaffold placeholder.
Read `AGENTS.md`, `kb/HANDOFF.md`, `kb/features.md`, and `docs/ORACLE_DEPLOYMENT.md`.

Branches `main`, `derek-dev`, and `abdul-dev` each publish only their own Oracle stack.
Production changes require an authorized, checked PR into main. Each environment has
independent data, runtime secrets, OAuth client, image package, updater and backup.

Run `python scripts/app.py check` for backend tests, browser regressions and the production container. Linux CI additionally
runs the updater recovery harness and complete-state backup tests. Local development
uses `app.ps1`/`app.sh`; stateful updates quiesce the local service and copy its whole
`/data` to ignored `.runtime/backups` before replacement. Preserve those keys and
encrypted-token data; do not put `.runtime` or runtime.env into Git.

The API contract is in `docs/API.md`. Google/Gmail login and delivery still require live
acceptance. Infrastructure verification alone does not establish feature acceptance.
