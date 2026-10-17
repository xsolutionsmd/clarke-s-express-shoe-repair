# clarke-s-express-shoe-repair lifecycle

Requirements: Python 3.10+, Git, Docker Engine/Desktop using Linux containers and Compose v2. Application dependencies build in containers.

Clone this repository on dev for development. Run `bash start.sh` or `.\app.ps1 start`; open http://127.0.0.1:8787. Source is mounted from `app/`; restart/reload behavior is supplied by the application's development command. Run `bash update.sh` or `.\app.ps1 update` to fetch the current dev/main branch, refuse dirty/ahead/divergent history, fast-forward and rebuild before replacement. Updating dev leaves main and server releases alone.

`bash app.sh doctor` checks host tools. `bash app.sh check` runs container tests and an isolated production-image health/revision check. PowerShell uses `.\app.ps1 doctor` and `.\app.ps1 check`.

Installed local preview: `bash start.sh --mode installed`; update with `bash update.sh --mode installed`. PowerShell uses `.\app.ps1 start -Mode installed` and `.\app.ps1 update -Mode installed`. First start discovers current main's exact release image; subsequent starts retain the saved image. Update discovers the current main release, validates its digest/revision and preflights it before replacement. An explicit `--image ghcr.io/xsolutionsmd/clarke-s-express-shoe-repair@sha256:<digest>` / `-Image` overrides discovery. Private repositories additionally need authenticated GitHub CLI and Docker registry pull access. Missing/unpublished/invalid releases preserve the running installation. The installed image is remembered in ignored `.runtime/installed.json`. Development and installed modes have separate persistent volumes. `stop` removes containers and networks but retains their data. Both default to the same local port; stop one mode first or provide distinct `--port` / `-Port` values.

Each clone generates a stable `.runtime/installation-id` used in its resource names. Preserve that identity with the installation record; a fresh second clone must have its own runtime folder. Development mounts `app/` directly at `/workspace`, so its command uses paths relative to that source directory.

Develop on dev or feature branches targeting dev. Main is the release gate and merging into it requires release authorization. Configure main protection, required checks and the main-only production environment in GitHub. The selected host is **oracle**. The host adapter supplies deployment, manual release, origin verification and recovery; generated common CI alone does not prove deployment.

Follow [production release compute](docs/RELEASE-COMPUTE.md): private source repositories default to release tests/builds on the prepared local PC environment; public repositories use standard GitHub-hosted runners. Verify live application-repository visibility first. The generated hosted CI is a public-route template: integrate the existing local release contract for private apps before enabling publication. This scaffold does not provision local release runners. For private local failures, attempt bounded repair, then use an established server build/test route or standard GitHub-hosted minutes if blocked or inaccessible. This fallback is authorized within an authorized release; report it and rerun all required tests.

Before releasing a stateful app, define and test backups, migrations and restore behavior. Image rollback preserves mounted data and cannot undo a data migration. Keep credentials/private runtime out of Git and the Docker context. Record actually tested revisions, URLs, image digests and limitations in the app's validation record.

Whole-repository development context is included: follow [Graft setup](docs/GRAFT.md) after the first local commit and configuring origin. Keep its tools and caches outside the production Docker context. Browser applications keep [Reticle runtime verification](docs/RUNTIME-VERIFICATION.md) available with per-task use opt-in; skip it unless requested. The scaffold supplies the procedure, not a framework-specific SDK installation. An explicit setup request includes an initial integration check or a concrete compatibility blocker. Ordinary tests and release gates remain required. Non-browser apps record it as not applicable.

## Branch contract

This repository has no shared dev branch. Long-lived branches: `main` (production) and `derek-dev`, `abdul-dev` (personal preview environments). Wherever this guide says dev, use your own preview branch; promote with a reviewed PR from it into main, then merge main back into each preview branch.
