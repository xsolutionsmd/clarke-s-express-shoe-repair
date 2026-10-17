# Validation

## Current release acceptance, 2026-10-17

The accepted application revision is `42235a04b629b5ee53669365dd48446d70f87f6e`.
The original visual/runtime acceptance at `37fd564eb87aeffb6223d70b482c1662d483d57e`
is preserved below and in build-receipt history. The later decoder correction passed
[hosted CI](https://github.com/xsolutionsmd/clarke-s-express-shoe-repair/actions/runs/39064984447)
with 138 backend/API and 83 browser cases. Both required PR checks passed at that
exact head. The focused R8 review found no actionable issue; 14 strict health-verifier
cases and six isolated stack-limit checks passed. No frontend change required a new
design review. All 45 pre-release rows pass.

PR [#2](https://github.com/xsolutionsmd/clarke-s-express-shoe-repair/pull/2) was merged
through the protected release path as `f8d72bd8f7ef84a0814c8706ad6a02887f86b4fc`.
The [main push workflow](https://github.com/xsolutionsmd/clarke-s-express-shoe-repair/actions/runs/39066415945)
passed and production independently matched that revision over HTTPS. Main is merged
back to both preview branches; later preview commits carry operating records only.

R9 completed all 13 live rows under the user's final single-account constraint.
Each environment used the existing Admin's real Chrome Google session, connected
its own Gmail sender with the existing send-only grant, and completed a 375px
photo request, $12.34 synthetic estimate, customer acceptance, and ready-for-pickup.
Five messages per request were observed in the actual allowlisted Gmail Inbox:
customer receipt, staff alert, estimate, customer-response alert and ready notice.
Sent outbox entries alone were not treated as inbox evidence.

Real session revocation in a second tab was followed by the normal Google account
chooser and same-member return; the amount and estimate text were restored in each
environment. Nine anonymous admin collections returned 401/AUTH_REQUIRED. Customer
status pages excluded contacts, photos and internal notes. Notices appeared on the
customer status surface and expired without refreshing it; current Bel Air hours
returned and Dundalk remained appointment-only. The genuine 12 MP HEIC additionally
converted on the live ARM64 Derek preview in 2.807s during R7.

The user explicitly excluded separate-account live Viewer acceptance. That flow
was not completed or marked passed. Its local Viewer/invitation tests remain valid
pre-release evidence only. All temporary invitations were withdrawn through Admin
controls; no invitation mail was sent and no second member was added. The existing
Admin, original allowlists and demo restrictions are preserved.

Exact synthetic request/photo IDs, including the retained R7 request, were purged
after protected backups. Every environment has zero remaining requests and no
active test notice. Audit and backup history remain. Backup/update timers are
active; the 12 sibling containers, nine HTTPS revisions and gateway remained
unchanged. A harmless Derek-only KB commit `a9c99be01cf66d3698a8af66cbddb00d5826d2bf`
changed only Derek's container/revision, with production and Abdul identical to
the captured baseline. Its [preview workflow](https://github.com/xsolutionsmd/clarke-s-express-shoe-repair/actions/runs/39067543054)
passed. Final operating-record commits are verified separately at each branch head.

Owner policies remain demo defaults. No operational handover or off-server
disaster recovery is claimed. Private R9 receipts retain exact IDs, inbox evidence,
final branch revisions, immutable image identities, cleanup and sibling checks.

The dated sections below are historical checkpoints; their earlier pending/failure
statements do not override the current evidence above.

## First release checks, 2026-10-17

The first hosted check at 6a8d4f9 failed the real 12 MP HEIC conversion with
IMAGE_LIMIT_EXCEEDED; 136 other backend cases passed. A trial allocator cap did
not fix it and was removed. Diagnostics found CI inherited a 16 MiB stack; the
same setting reproduced the handled memory error locally. The decoder now
re-execs with its stack bounded to 8 MiB before reading an image, preserving
stricter inherited limits. Its 160 MiB address-space, CPU, time and sandbox
limits are unchanged. All nine upload cases pass under CI's inherited stack
and the real 256 MiB container cap, including real HEIC cases with 8 and 16 MiB
inherited stacks. Hosted checks must pass before publishing this correction.
The original reviewed build receipt remains at 37fd564; this targeted release
correction is recorded separately. No frontend change requires a layout review.

## Accepted pre-release build, 2026-10-17

Committed runtime 37fd564eb87aeffb6223d70b482c1662d483d57e passed the final combined
check with exit 0: 134 backend and 81 browser cases plus lint/build/runtime checks.
The coordinator completed the affected desktop/tablet/phone visual pass and retained
the main-flow recordings. All 45 pre-release acceptance rows now pass.

Four targeted follow-up scenarios close the evidence gaps: real intake thresholds,
paused contact actions, SQLite-contention 503/offline recovery, and same-member
session re-entry with a retained estimate and stale-version guard. Four backend/API
cases and four browser scenarios passed. These changes add tests only; application
code is unchanged. The coordinator checked all four returned test-file hashes.

Actual Google/Gmail and all 13 live rows remain unverified pending release. Real
provider success, physical printing and operational owner approval are not claimed.

## Functional review fixes, 2026-10-17

The final local implementation suite passed 134 backend tests and 81 Chromium browser
cases, plus lint, frontend/static build, runtime fixture exclusion, health, revision and
source-label checks. The coordinator verified the recorded hashes for all 28 changed
source/test files. The older blocked-build notes below are historical.

All 11 code-review findings and eight coordinator findings were accepted and fixed.
Regressions cover failed logout, expired/cleared photo drafts, delayed navigation,
private status history isolation, recoverable read errors, pending retention and
explicit comparison before reapplying stale staff drafts. Browser evidence covers
portrait-photo fit, doubled text, reduced motion and print-media/PDF generation;
physical printing and a human PDF visual review are not claimed.

The PowerShell redirected wrapper reported status 1 despite the launcher's final
success and completed test results; native stderr handling was reproduced separately.
A committed-candidate verification and affected-page walkthrough follow. Actual
Google/Gmail and all live acceptance rows remain outstanding. No functional deployment
is claimed by this local result.

## Local backend implementation, 2026-10-17

Independent backend review reproduced five defects and one browser-test gap.
Local fixes now pass 121 backend/API tests, 61 recovery tests and 54 updater cases.
They cover environment-bound restore preflight, ready-email preservation, midnight
submission replay, query-bound keyset pagination, backward offer transitions and
a stronger duplicate-submission assertion. Recovery host actions were mocked;
the updated backup scripts have not been installed or verified on Oracle.
The strengthened browser test is collected, not executed. Final combined review
and frontend acceptance remain open.

69 backend tests passed under the 256 MB read-only container limits, including
authentication/roles, concurrency, DST, demo outbox behavior and genuine 12 MP HEIC
conversion with metadata removal. `python scripts/check_backend.py` passed actual
HTTP intake, container replacement and complete SQLite/uploads/key restoration.
Parent verified all 44 source hashes recorded by the backend test receipt.

Combined `python scripts/app.py check` is blocked at `npm ci`: the partial frontend
package and lock differ. Referenced admin styles and management views are also
missing. 44 Playwright cases are collected but have not executed. No full build,
browser walkthrough, actual Google/Gmail, live feature or acceptance pass is claimed.
Provider tests use isolated process fixtures; production images contain no login
bypass. All 45 pre-release and 13 live acceptance rows remain fail/unverified.

## Infrastructure validation

2026-10-17 Part A: initial placeholder container check passed at `0e3209d`:
container health, source label, exact revision and static build checks. The Linux
updater harness exercises first/subsequent deployments and rollback with synthetic
data, without host/network access. An initial Derek preview allowlist mismatch was
detected by the harness; its escaped package suffix is corrected in source and on
the host before successful preview publication.

The daily backup adaptation includes SQLite, uploads, session/encryption keys and
matched runtime/release configuration. Tests verify extraction and reject archive
traversal. Live verification must cover all three HTTPS placeholders, noindex,
branch-head revision, container replacement persistence and complete backup restore.
Detailed operator receipts are kept outside the public source.

No repair UI/API, Google login, Gmail delivery, feature acceptance or owner operation
is claimed by this infrastructure-only stage. DEMO_MODE stays true.
