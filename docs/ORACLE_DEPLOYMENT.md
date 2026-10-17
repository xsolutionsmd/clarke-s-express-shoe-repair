# Oracle application deployment

The functional repair application replaces the Part A placeholder. Production and
both previews remain noindex with `DEMO_MODE=true`. R9 verified authentic Google
sign-in and same-member draft restoration, separate Gmail connections, and actual
allowlisted inbox receipts on every environment. The user restricted live testing
to the existing Admin account, excluding separate-account Viewer acceptance. All
temporary invitations were withdrawn without sending invitation mail.

First production release: PR [#2](https://github.com/xsolutionsmd/clarke-s-express-shoe-repair/pull/2),
merged as `f8d72bd8f7ef84a0814c8706ad6a02887f86b4fc`. Reviewed application revision:
`42235a04b629b5ee53669365dd48446d70f87f6e`. Later preview commits update operating
records only. Check each origin's `/version.json` against its own branch head after
every final push; the private operator receipts retain the observed revisions/digests.

See `deploy/oracle-contract.json` for exact independent identities. Production uses
`main`; each personal preview publishes on push to its own branch. Main requires a
PR and both `Check deployable app` and `Check application container`. Public source
uses GitHub-hosted checks/builds, immutable GHCR digests and exact-revision releases.
No workflow deploys another branch's image. Preview releases are never latest.

## Runtime

Each `/opt/<slug>/data` is a separate bind mount at `/data`, owned by UID/GID 10001,
mode 0700. SQLite (`clarke.sqlite3`), uploads and Oasis-compatible `secret.key` and
`encryption.key` belong here. Each root-owned `runtime.env` is mode 0600. The app
container runs read-only, with `/tmp` disposable, no host port, a unique proxy alias,
256 MB memory and 100-process limits. Gateway request limit is 55 MB; the application
must enforce its own per-file/count/type rules. Only the gateway publishes HTTPS.

The runtime contract uses `PUBLIC_ORIGIN`, `DATA_DIR`, `DEMO_MODE=true`,
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `INITIAL_ADMIN_EMAIL`, and the legacy
Oasis `OPERATOR_EMAIL` alias. `SESSION_SECRET` and `ENCRYPTION_KEY` are unique per
environment, mirrored to Oasis key files. The backend must preserve those files.
The application consumes `DEMO_ALLOWED_EMAILS`, `DEMO_ALLOWED_PHONES` (E.164) and
`NOTIFICATION_EMAILS`; their private values never enter Git or images. All three
environments have independent protected keys, data and OAuth clients.

## Google setup

Use one Web application OAuth client per environment in X Solutions Booking.
The authorized origin is its exact HTTPS origin and the only redirect URI is that
origin plus `/oauth/callback` (the existing Oasis convention, shared by sign-in and
Gmail-sender connection). All three exact URLs are in the deployment contract.
Set each pair only in its environment's runtime.env, then recreate that service.
Do not reuse another site's client or sender token. Initial admin and test-recipient
values are provisioned privately. Client creation alone does not prove sign-in or
email delivery. Use the authentic invited Google account at `/admin/login`, connect
the sender through Admin Emails, and verify actual inbox receipt for allowlisted
tests in each environment. Never install a synthetic staff session on a live site.

## Installation and updates

Install reviewed `server/` plus `compose.production.yaml`; run the production or
matching preview `install.sh` as root. Installers preserve an existing timer state;
new update timers stay paused until routes are validated. Enable the three timers
after Caddy is ready. Root-owned host scripts are installed explicitly, never from
downloaded release data. Daily backup timers start on installation.

The updater is adapted from the tested Oasis transaction: validate manifest and
image identity, test a network-isolated candidate with disposable state and no
credentials, quiesce the old service, snapshot all data and runtime configuration,
replace, verify exact HTTPS revision, then commit the receipt. Failure restores
matched data/config/image. An interrupted or failed recovery leaves `transaction`
and its recovery directory; subsequent polls refuse to overwrite that evidence.
The functional image includes the candidate probe dependencies. `/health` returns
exactly `{"status":"ok"}`; `/version.json` is uncached and reports the image revision.
The reviewed environment-bound backup/updater scripts and units were installed on
all three stacks before release, with protected runtime configuration and keys
preserved. Both update and backup timers are enabled and active.

## Backup and restore

`sudo <slug>-backup` takes a brief service pause, checks SQLite integrity, copies
the complete data directory (including uploads/keys), and saves runtime.env,
Compose, release.env and current.json in a root-only archive under
`/var/lib/<slug>-deploy/backups`. The service resumes before archive compression.
This is a same-disk recovery set, not off-server disaster recovery. Archives are
retained pending a deliberate retention policy; review storage at owner handover.

Restore with the environment's update timer paused:

```sh
sudo systemctl stop <slug>-update.timer
sudo <slug>-backup --restore /var/lib/<slug>-deploy/backups/<archive>.tar.gz
# Inspect exact HTTPS revision and application data before resuming publication.
sudo systemctl start <slug>-update.timer
```

Restore first preserves the current data in another complete archive. Failed restore
leaves a refusal guard and the recovery archive path; keep the timer paused, inspect
the files, and restore the matched data/configuration before clearing the guard.
Never remove shared gateway/certificate resources or prune Docker globally.
Image retention is separately registered per environment, retaining current plus
two prior successfully observed releases. It does not delete application data.

## Verification scope

`scripts/test_updater.py [--branch derek-dev|abdul-dev]` exercises first/subsequent
success, absent/stale/malformed manifests, architecture/candidate/replacement/HTTPS
failures, snapshot/state/TERM recovery, failed rollback and interruption guard.
`scripts/test_backup.py` covers complete SQLite/uploads/keys/config archives and
unsafe extraction rejection. Live Part A drills additionally replace each real
container and restore its synthetic SQLite/file fixture, then remove test data.

R9 additionally completed 375px photo intake, estimate/accept/ready, customer privacy,
notice creation and automatic expiry, exact synthetic cleanup, and the Derek-only
branch isolation proof. All three retain one genuine Google-bound Admin, no pending
invitations or active test notices, and zero test repair records. Backups and audit
history are preserved. Operational owner approval and off-server recovery remain
separate from this demo release.
