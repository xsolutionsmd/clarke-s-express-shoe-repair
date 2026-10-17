# Oracle infrastructure

Part A installs only the scaffold placeholder. The repair application, Google sign-in
routes, Gmail connection and business acceptance tests remain the next build stage.
The placeholder is noindex in every environment.

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
Private test-recipient settings never enter Git or images.

## Google setup

Use one Web application OAuth client per environment in X Solutions Booking.
The authorized origin is its exact HTTPS origin and the only redirect URI is that
origin plus `/oauth/callback` (the existing Oasis convention, shared by sign-in and
Gmail-sender connection). All three exact URLs are in the deployment contract.
Set each pair only in its environment's runtime.env, then recreate that service.
Do not reuse another site's client or sender token. Initial admin and test-recipient
values are provisioned privately. Client creation alone does not prove sign-in or
email delivery; the application stage must connect and test them.

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
The placeholder candidate uses wget; a future backend image must provide wget or
explicitly update and retest the candidate probe when changing runtime stacks.

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
