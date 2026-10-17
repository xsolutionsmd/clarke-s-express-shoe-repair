# Whole-repository context

This repository includes a local Graft adapter for Codex development across application
code, Dockerfiles, Compose, CI, deployment scripts, docs and configuration. Supported
languages get structural graph queries; other permitted text files use search/read.
Graft supplies context. Ordinary Git/release tools still make and publish changes.

Requirements: Python 3.10+, Git and Docker with Linux containers. Host Node is not
needed. Initialize dev, create a local commit and set origin to the repository named
in tools/graft/context.json before setup. Origin must use the canonical GitHub HTTPS
URL ending in .git or git@github.com SSH form. Do not push merely to initialize context.

```sh
python -B scripts/graft.py --ref dev setup
python -B scripts/graft.py --ref dev status
python -B scripts/graft.py --ref dev ask "application startup"
python -B scripts/graft.py --ref dev search "FROM"
python -B scripts/graft.py --ref dev read Dockerfile
python -B scripts/graft.py --ref dev read .github/workflows/app.yml
python -B scripts/graft.py --ref dev read runtime/nginx.conf
python -B scripts/graft.py --ref dev read runtime/vite.config.mjs
python -B scripts/test_graft.py
```

Search/read work without Docker. `--start-line 121 read PATH` continues a file;
reads are limited to 120 lines/12,000 characters and searches to 40 hits/12,000
characters. `ask` returns up to five graph excerpts plus text matches. `api PATH`
returns supported signatures; `callers SYMBOL` follows one hop. Remove the `source/`
prefix from graph paths when opening actual source. Read adjacent code and tests
before editing; missing edges do not prove absence. Use direct reads for small files.

`--ref` must match a configured long-lived branch. Branches come from
`xsolutions.json` environments first, then `app-workflow.json` branches, with
`dev` and `main` as the generic fallback. Invalid configurations are rejected.
Repositories with personal preview branches use `--ref <their-branch>`.
On an attached feature branch, use `--ref dev --feature` (or the configured preview
base) on every command; its cache identifies both that base and the actual branch.
Feature mode cannot bypass a mismatch between long-lived branches or use main.
Use a separate clean main worktree with `--ref main` for production-source context.
Do not reset or switch a dirty checkout to obtain it. Main context is not evidence
of what is running live. Detached HEAD, mismatched origin and dirty main are rejected.

`remote` uses authenticated gh CLI to read the configured repository's explicit
configured ref; `remote README.md` reads that ref's file. Feature mode reads
the selected development base remotely. Compare local and remote revisions rather than assuming they match.

The pinned bundle uses Graft 0.18.0, Node 22.22.0, a base-image digest and npm lockfile.
Setup builds and verifies the tooling image, then saves its immutable image ID.
Queries have no network, use a read-only container with temporary HOME, and mount
only a filtered repository snapshot. Tool definition changes require setup again.
No global hooks, cloud service, provider keys, paid summaries or MCP registration
are needed. [Upstream Graft](https://github.com/trailhq/Graft) is installed at build time.

`sourcePatterns: ["**"]` covers tracked eligible repository text. The adapter excludes
dependencies, binaries, large files, symlinks, submodules, private/runtime directories,
.env and known credential filenames. Only the authored root paths
`runtime/nginx.conf` and `runtime/vite.config.mjs` bypass the runtime exclusion;
other runtime paths stay excluded and .conf is not enabled generally. Both still
require tracked, bounded UTF-8 regular files without symlink traversal.
Check `status` for excluded tracked paths and
omitted untracked files. Review new files before intentionally staging them; filenames
cannot identify every secret. Never narrow the default to only the application folder.
For a new stack, inspect exclusions and extend the text policy with focused tests as needed.

Snapshots and graph caches live under ignored `.graft-context/`, separated by ref or
feature branch. Requests refresh tracked edits/deletions and check identity/source
hashes; concurrent use is locked. Remove a stale lock only after confirming no query
is running. `/graft/` is root-anchored in .gitignore so authored tools/graft stays tracked.
Keep tooling, snapshots and graph data outside the application's Docker allowlist.

The adapter tests use disposable Git fixtures and require no network or Docker.
Also verify a real graph query and infrastructure-file read before claiming setup
works. Record exact versions and limitations; do not promise token savings.
Removal is scoped to this checkout's tooling/cache; preserve app data and avoid
global Docker pruning or deleting an image still used by another checkout.
