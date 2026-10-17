# Production release compute

User-confirmed default, September 21, 2026. Apply to production release testing
and image builds across projects, unless the current request explicitly selects
another route. Repository visibility determines compute; the server destination
does not.

| Verified source repository visibility | Default release test/build compute |
|---|---|
| Private | Derek's local PC using the prepared release environment; avoid GitHub-hosted minutes |
| Public | Standard GitHub-hosted runners, using the repository's release workflow |

Read live visibility for the actual application repository, for example
`gh repo view OWNER/REPO --json nameWithOwner,visibility`. Check the returned identity.
Do not infer it from the public release-environment tooling repo, the website URL,
the GHCR package, cached memory or the project name. If visibility is unavailable
or neither PUBLIC nor PRIVATE, resolve that before dispatching release compute;
continue independent preparation. Never make private source public to save minutes.

For private apps, reuse the established local environment and its app-specific
release contract. For apps already supported by Derek-Sykes/release-environment,
select `release.ps1 local` or `./release.sh local`; for supported public apps select
the corresponding `github` route. Inspect that launcher's current README and app
contract before use. Its existing VoiceVault integration is not proof that an
arbitrary Oracle/new app is already supported. Adapt and validate missing support
before dispatch, preserving the app's tests, manifest and updater.

For private local failures, diagnose and attempt a bounded repair. As an operating
heuristic, try one or two targeted fixes or roughly 10–15 minutes of active diagnosis;
this is not a user-set timer. Continue only while there is clear near-term progress.
If the PC/environment is inaccessible or the blocker cannot reasonably be repaired,
fall back promptly. Prefer an already configured, accessible server build/test route
when suitable; otherwise use standard GitHub-hosted runners and the normal Actions
minutes. Derek explicitly authorized this fallback on September 21: no further
confirmation is needed within an already authorized release. Explain the reason
and selected route in the progress/release receipt. Do not raise spending limits
or provision premium runners under this preference.

A deploy-only server runner is not automatically a build runner. Use only an
established isolated build/test environment with suitable capacity, keeping live
services and production data out of tests. If none exists, go directly to hosted
compute rather than building a new server setup just to avoid minutes.

Fallback reruns the required tests; it never waives them. Environment-specific
failures may be resolved by changing compute, but a reproducible application defect
must be fixed and all required gates must pass before publication. Do not rerun
indefinitely until a flaky test happens to pass. Resolve active/ambiguous runs before
retrying and preserve the selected source/request identity. If an application fix
changes source, promote it through the normal route and explicitly select/test the
new revision. Public hosted execution remains the default; better speed/reliability
is a preference, not a measured guarantee.

GitHub may orchestrate a local self-hosted job without using GitHub-hosted build
minutes. Check every release job, including helper/verification jobs, before claiming
the private release consumes none. Use ephemeral trusted-main local runners with
the existing isolation/cleanup contract; never route untrusted PR code to the
privileged local Docker runner. Existing PR/dev CI is a separate policy: inspect
and report its usage without disabling required checks as a side effect.

Standard hosted compute is free for public repos under [current GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
Larger runners are charged separately. Recheck terms when relevant; no paid runner
upgrade is implied. This preference makes no claim about registry/storage/hosting costs.

Test the exact release candidate and publish/deploy that tested artifact by immutable
digest with the correct target architecture. Keep health, backup/migration and live
verification gates. Private-network deployment may still use the existing server
runner, or Oracle's updater, regardless of where the image was built. Preserve each
app's manual/automatic release policy and current release authorization. Avoid a
duplicate full local release build before a public hosted build unless a specific
local-only concern requires it. Local development previews remain available.

When creating or adapting a workflow, choose this route before enabling push/main
publication. Hosted example templates are the public route; they do not automatically
implement private local execution. Wire and verify the local release contract for a
private app before enabling its publisher. Do not claim a saved skill preference has
already changed an existing repository's YAML or deployed anything.

Record repository identity/visibility, selected route, source SHA, tested image digest,
actual job runners and separate CI/live results in the release evidence.

## Local Docker cleanup preference

September 24, 2026 confirmed correction: remove finished disposable containers,
images, networks and synthetic volumes promptly. Retain only active resources or
those with a concrete near-term use, and record that reason/recheck at handoff.
Published source can be rebuilt; indefinite speculative reuse is insufficient.
Inspect exact ownership/mounts and preserve application data, secrets, tool homes,
backups and unrelated active work. Use explicit identities, never global pruning.
Do not infer that disk usage caused a reported crash without diagnostic evidence.
This does not authorize changing a server's protected recovery-image retention.

Owner clarification September 24: keep the designated VoiceVault local test
environment available as a standing exception, including its container services,
current image and required state. Do not remove it as disposable test output.
Recheck this exception only if the owner retires or replaces that environment.

Owner clarification September 25: permanently retain the current designated
VoiceVault local test environment's build cache because it is used frequently.
This cache exception applies only to that standing environment, not disposable
release/test builds. After a rebuilt replacement is verified and active, remove
superseded local-test images and obsolete cache by exact identity. Keep only the
current version and the cache/layers it needs; preserve shared dependencies and
persistent application data. A source bind-mount edit alone does not require a
new image. Inspect references before cleanup; never use a global prune.
