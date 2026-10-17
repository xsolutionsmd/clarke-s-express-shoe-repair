<!-- xs-company:start -->
# Clarke's Express Shoe Repair — X Solutions client website

This repository is the complete, portable working record for Clarke's Express Shoe Repair's website:
source, deployment configuration **and** the company knowledge base in `kb/`.
Any agent (Codex, Claude or another) that clones it should be able to continue
without Derek's or Abdul's private workspace.

## Resume here

1. Read `kb/HANDOFF.md` first: current state, last change, open work and next step.
2. Read `kb/INDEX.md`, then only the KB files your task needs. `kb/design-brief.md`
   holds the accepted direction and X Solutions' standing design rules; read it
   before any visual change.
3. Read `xsolutions.json` for identity, environments and pipeline stage status.
4. Check `git log -5` and your own preview environment's live `/version.json`.

When you finish a working session, update `kb/HANDOFF.md` (what changed, what is
verified, what is next) and any KB file whose facts changed, in the same commit as
the work. If the XSolutions skills are installed, `xs_company.py handoff` also
refreshes the generated status block.

## Branches and environments

| Branch | Environment | URL |
|---|---|---|
| `main` | production | https://clarke-s-express-shoe-repair.xsolutionsmd.com |
| `derek-dev` | derek-dev | https://clarke-s-express-shoe-repair-derek-dev.xsolutionsmd.com |
| `abdul-dev` | abdul-dev | https://clarke-s-express-shoe-repair-abdul-dev.xsolutionsmd.com |

- There is no shared `dev` branch. Derek works on `derek-dev`; Abdul works on
  `abdul-dev`. Pushing to your branch deploys **only** your preview.
- Production changes go through a reviewed PR from a preview branch into `main`;
  merging deploys production automatically. Merging into `main` needs release
  authorization from Derek or Abdul for that change.
- After a production release, merge `main` back into both preview branches.
- Do not push to the other person's branch without asking them. The one exception is
  the initial pipeline run, which syncs all three branches.

## Rules for this repository

- It is public. Commit only sourced public business facts, the design brief and
  project state. Pricing, quotes, lead/sales status, private contact details,
  credentials and raw media of unclear permission stay out (they live in X
  Solutions' private workspace or Slack). Run `xs_company.py check-public` before
  pushing when the skills are installed.
- Every factual claim on the site must trace to `kb/sources.md`. Unknowns stay
  unknown; never invent reviews, ratings, prices, credentials or service areas.
- Media: the site is built for the business, so all of the business's collected
  media may be used in every environment (see `kb/media.md`). The original media library was delivered to
  Abdul on Slack.
- Previews are `noindex` and use test data and test integrations only.
- Keep `kb/`, `AGENTS.md`, `CLAUDE.md` and `xsolutions.json` out of the production
  image (`.dockerignore`).
<!-- xs-company:end -->

# Repository development

Read the README, WORKFLOW.md and current validation record before changing the app.
For a new website, new app interface or substantial visual redesign (including
“build me a beautiful website”), use the repository's
[reference-design skill](.agents/skills/reference-design/SKILL.md) and
[setup guide](docs/DESIGN_WORKFLOW.md). Complete requirements, visual references,
implementation and real desktop/mobile checks; ordinary backend fixes skip this.
Develop on dev or an explicit feature branch targeting dev. Preserve the configured
release policy; merging into main and publishing/deploying require release authorization.
An authorization already given for the current task remains effective.

Before publishing, follow [release compute](docs/RELEASE-COMPUTE.md): verify the app
repository's live visibility; private repos use the prepared local PC environment
for release tests/builds, public repos use standard GitHub-hosted runners. This
selects build compute, not production hosting or release authorization.

Use [Graft](docs/GRAFT.md) for whole-repository discovery: application source,
Dockerfiles, Compose, CI, deployment scripts, configuration and documentation.
Use its bounded text search/read or direct source reads where graph coverage is absent.
Inspect status for the actual repository, branch, revision and excluded/untracked paths.
Do not treat graph results as proof that a behavior works or as authority to deploy.

For browser behavior, follow [runtime verification](docs/RUNTIME-VERIFICATION.md).
Keep Reticle available but use it only when requested for the task; do not ask every
time. A full pass with Reticle combines normal suites and selected browser flows.
Keep required tests and direct desktop/mobile inspection regardless. When Reticle
is selected, verify a connected session before claiming observations.
Record genuine failures and unknown observations; a missing connection is not a pass.
Keep context caches, runtime recordings, credentials and developer tooling out of
production images. Separate local, container, CI and live evidence in the validation record.

## Branch contract

This repository has no shared dev branch. Long-lived branches: `main` (production) and `derek-dev`, `abdul-dev` (personal preview environments). Wherever this guide says dev, use your own preview branch; promote with a reviewed PR from it into main, then merge main back into each preview branch.
