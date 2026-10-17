#!/usr/bin/env python3
"""Install the shared Oracle image-retention policy and register one app."""
import argparse
import ast
import os
from pathlib import Path
import re
import subprocess
import tempfile
from app_image_retention import POLICY_VERSION, configs, read_json, validate_config

CONFIG_DIR = Path('/etc/app-launchpad/image-retention.d')
STATE_DIR = Path('/var/lib/app-launchpad/image-retention')
ENGINE = Path('/usr/local/sbin/app-image-retention')
UNIT_DIR = Path('/etc/systemd/system')

SERVICE = '''[Unit]
Description=Retain current and two previous successful application images
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/app-image-retention sweep
TimeoutStartSec=10min
UMask=0077
Nice=10
IOSchedulingClass=idle
'''

TIMER = '''[Unit]
Description=Hourly automatic application image retention

[Timer]
OnBootSec=5min
OnUnitInactiveSec=1h
AccuracySec=1min
Unit=app-launchpad-image-retention.service

[Install]
WantedBy=timers.target
'''


def install(path, content, mode):
    if path.is_symlink():
        raise ValueError('Refusing to replace symbolic file: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    staged = Path(temporary)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(staged, mode)
        os.chown(staged, 0, 0)
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def trusted_directory(path):
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise ValueError('Symbolic operational directory: ' + str(parent))
        if parent.exists():
            info = parent.stat()
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError('Operational directory must be root-owned and not writable by others: ' + str(parent))


def engine_version(path):
    for statement in ast.parse(path.read_text(encoding='utf-8')).body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'POLICY_VERSION' for target in statement.targets):
            value = ast.literal_eval(statement.value)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    raise ValueError('Installed shared policy has no supported version; review migration')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--service', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Install with sudo')
    config = validate_config(read_json(args.config))
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,60}\.service', args.service):
        parser.error('Invalid updater service')
    subprocess.run(['docker', 'version', '--format', '{{.Server.Version}}'], check=True)
    subprocess.run(['systemctl', 'cat', args.service], check=True, stdout=subprocess.DEVNULL)
    for directory in [CONFIG_DIR, STATE_DIR, UNIT_DIR, ENGINE.parent]:
        trusted_directory(directory)
    trusted_directory(Path(config['state_dir']))
    existing = configs(CONFIG_DIR) if CONFIG_DIR.exists() else {}
    for name, previous in existing.items():
        if name == config['name']:
            if previous != config:
                raise ValueError('Existing app policy differs; review its migration before reinstalling')
        elif set(previous['repositories'].values()).intersection(config['repositories'].values()):
            raise ValueError('Another app already manages this package')
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o755)
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE_DIR, 0o700)
    source = Path(__file__).with_name('app_image_retention.py')
    compile(source.read_text(encoding='utf-8'), str(source), 'exec')
    if ENGINE.exists():
        installed_version = engine_version(ENGINE)
        if installed_version > POLICY_VERSION or (installed_version == POLICY_VERSION and ENGINE.read_bytes() != source.read_bytes()):
            raise ValueError('Refusing shared-policy downgrade or unversioned change; review and version the shared upgrade')
    dropin = UNIT_DIR / (args.service + '.d') / '50-app-image-retention.conf'
    # A shell fallback also records uncertainty if Python itself cannot start.
    # App availability is preserved, but cleanup stays paused until history is reconciled.
    desired = ("[Service]\nExecStartPost=/bin/sh -c '/usr/local/sbin/app-image-retention observe --app " + config['name'] + " || { /usr/bin/touch /var/lib/app-launchpad/image-retention/" + config['name'] + ".uncertain; exit 0; }'\n").encode()
    if dropin.exists() and dropin.read_bytes() != desired:
        raise ValueError('Existing observer override differs; review it before replacement')
    install(ENGINE, source.read_bytes(), 0o755)
    install(CONFIG_DIR / (config['name'] + '.json'), args.config.read_bytes(), 0o644)
    install(UNIT_DIR / 'app-launchpad-image-retention.service', SERVICE.encode(), 0o644)
    install(UNIT_DIR / 'app-launchpad-image-retention.timer', TIMER.encode(), 0o644)
    install(dropin, desired, 0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'app-launchpad-image-retention.timer'], check=True)
    print('Registered ' + config['name'] + '; hourly retention enabled, successful-release observer installed. No app container restarted.')


if __name__ == '__main__':
    main()
