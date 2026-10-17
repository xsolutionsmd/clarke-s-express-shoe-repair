# Validation

## Local backend implementation, 2026-10-17

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
