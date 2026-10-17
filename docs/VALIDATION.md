# Infrastructure validation

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
