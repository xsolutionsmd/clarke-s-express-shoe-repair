#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo on the prepared server.' >&2; exit 1; }
cd "$(dirname "$0")/../.."
for command in docker curl git python3 flock timeout sync systemctl; do command -v "$command" >/dev/null; done
docker compose version >/dev/null
docker network inspect xsolutions-proxy >/dev/null
[[ $(uname -m) == aarch64 ]] || { echo 'This installation expects ARM64.' >&2; exit 1; }
for path in /opt/clarke-s-express-shoe-repair-derek-dev /var/lib/clarke-s-express-shoe-repair-derek-dev-deploy /usr/local/share/clarke-s-express-shoe-repair-derek-dev; do
  [[ ! -L "$path" ]] || { echo 'Installation directories must not be symlinks.' >&2; exit 1; }
done
was_active=false
if systemctl is-active --quiet clarke-s-express-shoe-repair-derek-dev-update.timer; then was_active=true; fi
if systemctl cat clarke-s-express-shoe-repair-derek-dev-update.timer >/dev/null 2>&1; then systemctl stop clarke-s-express-shoe-repair-derek-dev-update.timer; fi
if systemctl cat clarke-s-express-shoe-repair-derek-dev-update.service >/dev/null 2>&1; then systemctl stop clarke-s-express-shoe-repair-derek-dev-update.service; fi
install -d -o root -g root -m 755 /opt/clarke-s-express-shoe-repair-derek-dev /usr/local/share/clarke-s-express-shoe-repair-derek-dev
install -d -o root -g root -m 700 /var/lib/clarke-s-express-shoe-repair-derek-dev-deploy
install -d -o 10001 -g 10001 -m 700 /opt/clarke-s-express-shoe-repair-derek-dev/data
test -f /opt/clarke-s-express-shoe-repair-derek-dev/runtime.env || { echo 'Prepare /opt/clarke-s-express-shoe-repair-derek-dev/runtime.env with mode 600 before installation.' >&2; exit 1; }
chown root:root /opt/clarke-s-express-shoe-repair-derek-dev/runtime.env
chmod 600 /opt/clarke-s-express-shoe-repair-derek-dev/runtime.env
# Serialize administrator installation with any directly invoked updater too.
exec 9>/var/lib/clarke-s-express-shoe-repair-derek-dev-deploy/update.lock
flock -w 120 9
install -o root -g root -m 644 server/derek-dev/compose.yaml /usr/local/share/clarke-s-express-shoe-repair-derek-dev/compose.yaml
install -o root -g root -m 755 server/derek-dev/update-release.sh /usr/local/sbin/clarke-s-express-shoe-repair-derek-dev-update
install -o root -g root -m 755 server/derek-dev/backup.py /usr/local/sbin/clarke-s-express-shoe-repair-derek-dev-backup
install -o root -g root -m 644 server/derek-dev/clarke-s-express-shoe-repair-derek-dev-backup.service /etc/systemd/system/clarke-s-express-shoe-repair-derek-dev-backup.service
install -o root -g root -m 644 server/derek-dev/clarke-s-express-shoe-repair-derek-dev-backup.timer /etc/systemd/system/clarke-s-express-shoe-repair-derek-dev-backup.timer
install -o root -g root -m 644 server/derek-dev/clarke-s-express-shoe-repair-derek-dev-update.service /etc/systemd/system/clarke-s-express-shoe-repair-derek-dev-update.service
install -o root -g root -m 644 server/derek-dev/clarke-s-express-shoe-repair-derek-dev-update.timer /etc/systemd/system/clarke-s-express-shoe-repair-derek-dev-update.timer
# The retention observer and timer use this application's updater lock.
# Release our installation lock before installing the observer and shared timer.
flock -u 9
exec 9>&-
python3 server/retention/install_retention.py --config server/derek-dev/retention.json --service clarke-s-express-shoe-repair-derek-dev-update.service
systemctl daemon-reload
systemctl enable --now clarke-s-express-shoe-repair-derek-dev-backup.timer
if [[ "$was_active" == true ]]; then systemctl start clarke-s-express-shoe-repair-derek-dev-update.timer; fi
echo 'Installed clarke-s-express-shoe-repair runtime and automatic image retention; existing app timer state preserved. For first setup, prepare HTTPS route then enable --now clarke-s-express-shoe-repair-derek-dev-update.timer.'
