# Browser runtime verification with Reticle

Reticle is part of the default development setup for browser applications, including
business websites, but per-task usage is opt-in. Skip it unless requested; do not
ask every time. Keep normal required tests and release gates. Complete the
integration when setting up the actual app; the
Launchpad scaffold alone does not install an SDK. Non-browser apps record this as
not applicable. A concrete incompatibility requires a recorded blocker and direct
browser/network verification, not a silent skip or a fabricated pass.

## Usage modes

Reticle stays installed and available. Its use is opt-in for each task, following
the September 18 user clarification. Do not ask about it on every task; skip it
unless requested. A choice to use it remains effective for that task until changed.

- **Skip Reticle** (ordinary default): use the normal app URL and normal project
  checks. Do not start a preview or call Reticle tools. No uninstall is needed.
- **Use Reticle for this**: use the app's documented development integration and check the requested browser
  outcomes, rerunning only affected checks after fixes.
- **Run a full verification pass with Reticle**: after the batch of fixes, discover
  the current test commands from the README, development guide and CI definitions;
  run the applicable complete suites, then the selected browser flows with Reticle.
  Include existing saved scenarios where present; report flows that have no test.
  Use isolated synthetic state for mutations and preserve ordinary release gates.

A broad pass records revision, suite/flow, result, and failed/skipped/unknown coverage.
Do not label all behavior tested merely because Reticle assertions passed. Do not
start repeated mass runs or model-powered exploration without a request. This is
an on-demand agent workflow, not a new automatic test runner or scheduled job.
A full test request alone does not implicitly select Reticle.

For a local proxy integration, stop its preview and return to the normal app URL
to skip instrumentation. For framework integrations, document an explicit
development-only enable/disable switch and default it off. Keep packages and MCP
configuration available; MCP availability alone is not a connected app session.

## Set up against the actual stack

Use the [official Reticle setup](https://github.com/reticlehq/reticle#manual-setup--install--wire-it-yourself)
and [documentation](https://docs.reticle.sh) for the selected release. Inspect current
package versions and framework support; install exact compatible development
dependencies with the app's package manager and commit its lockfile. Use the
framework build plugin where supported, or an explicitly development-only entry
for plain HTML/custom builds. Do not change frameworks just to instrument the app.

Inspect installation behavior before running it. Upstream `init` can change multiple
agent configurations. Prefer manual scoped setup for this workflow: instrument this
app and connect its MCP server through the supported Codex configuration route.
Reuse a compatible existing server and avoid conflicting registrations or replacing
unrelated agent settings. Do not assume a Claude .mcp.json configures Codex. If client
reload is needed, record that pending step instead of declaring a connection.

Use isolated local development and synthetic records; keep trace/session data ignored
and outside production image context. Validate container-to-host connectivity when
the app runs in Docker. Use distinct automatically generated tab/session identities.
Start the app, open its page, confirm an actual connected session and run the installed
version's status/doctor checks where supported. Record package versions and commands
in the repository's README. These steps are based on upstream docs checked 2026-09-18;
recheck them at installation, particularly installer scope and platform behavior.

## Prove the changed behavior

Define an observable result from the real product requirement before driving the UI.
For a form/booking/save flow, exercise success, a controlled server failure, validation
and retry. Check the request, response and resulting persisted state; verify repeated
clicks do not create duplicate records when that is the app's requirement. Do not send
real messages, bookings or charges just to test. For a simple informational site,
check its meaningful navigation/CTA flow and browser errors without inventing a backend.

Cross-check important claims with browser network/server evidence. Lost sessions,
navigation gaps and incomplete request lineage mean unknown, never pass. Inspect
current upstream reports when affected (for example [full document navigation #898](https://github.com/reticlehq/reticle/issues/898)).
Reticle does not replace desktop/mobile visual inspection, accessibility checks or
application tests. Fix observed defects and repeat affected checks; avoid an endless
whole-site cycle after a targeted change has passed.

## Keep development instrumentation out of production

Build the actual production image and inspect emitted HTML/JS and installed runtime
dependencies for Reticle SDK/server code. Run that image locally and check browser
requests for development instrumentation/connections. Do not assume a devDependency
or a conditional call guarantees exclusion, especially for plain HTML. Keep the MCP
server and trace data out of the image as well. Record pass/fail/unknown, revision,
checked flow and remaining gaps alongside separate local/container/CI/live evidence.
