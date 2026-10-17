# Validation

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
