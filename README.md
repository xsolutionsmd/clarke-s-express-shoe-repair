# Clarke's Express Shoe Repair

The public-safe company KB, functional repair application and independent deployment infrastructure.
The application supports photo requests, private repair status, estimates, staff tickets,
and location hours/notices. The first functional release replaces the scaffold on
production and both previews. All environments remain noindex and in demo mode;
45 pre-release and 13 live acceptance rows pass within the recorded single-account
scope. Owner operational approval remains open.
Read `AGENTS.md`, `kb/HANDOFF.md`, `kb/features.md`, and `docs/ORACLE_DEPLOYMENT.md`.

Branches `main`, `derek-dev`, and `abdul-dev` each publish only their own Oracle stack.
Production changes require an authorized, checked PR into main. Each environment has
independent data, runtime secrets, OAuth client, image package, updater and backup.

Run `python scripts/app.py check` for backend tests, browser regressions and the production container. Linux CI additionally
runs the updater recovery harness and complete-state backup tests. Local development
uses `app.ps1`/`app.sh`; stateful updates quiesce the local service and copy its whole
`/data` to ignored `.runtime/backups` before replacement. Preserve those keys and
encrypted-token data; do not put `.runtime` or runtime.env into Git.

The API contract is in `docs/API.md`. Real Google sign-in, same-member re-entry,
Gmail delivery and actual test-inbox receipts passed independently on all three
environments. Separate-account Viewer acceptance was excluded by the user; local
Viewer/invitation coverage remains, without a live pass claim.

Production: https://clarke-s-express-shoe-repair.xsolutionsmd.com

Derek preview: https://clarke-s-express-shoe-repair-derek-dev.xsolutionsmd.com

Abdul preview: https://clarke-s-express-shoe-repair-abdul-dev.xsolutionsmd.com

Each origin's `/version.json` reports its own deployed branch revision. Staff enter
through `/admin/login`. See the current acceptance counts in `kb/features.md`.
