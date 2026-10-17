#!/usr/bin/env python3
"""Retain current + two proven prior image sets for explicitly registered apps."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

CONFIG_DIR = Path('/etc/app-launchpad/image-retention.d')
STATE_DIR = Path('/var/lib/app-launchpad/image-retention')
SLUG = r'[a-z][a-z0-9-]{1,39}'
REPOSITORY = r'ghcr\.io/[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9_.-]*'
POLICY_VERSION = 1


def now():
    return time.time()


def read_json(path):
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError('Unsafe or oversized JSON file: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_json(path, value):
    staged = path.with_suffix('.new')
    if staged.is_symlink():
        raise ValueError('Refusing symbolic state file')
    with staged.open('w', encoding='utf-8') as stream:
        os.chmod(staged, 0o600)
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    staged.replace(path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def validate_config(config):
    if not isinstance(config, dict) or config.get('schema') != 1:
        raise ValueError('Invalid retention configuration')
    for key in ('name', 'project'):
        if not re.fullmatch(SLUG, config.get(key, '')):
            raise ValueError('Invalid app identity')
    if not re.fullmatch(r'https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9_.-]+', config.get('source', '')):
        raise ValueError('Invalid source identity')
    repos = config.get('repositories')
    if not isinstance(repos, dict) or not repos or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', key) or not isinstance(value, str) or not re.fullmatch(REPOSITORY, value) for key, value in repos.items()):
        raise ValueError('Invalid image field/package mapping')
    if len(set(repos.values())) != len(repos):
        raise ValueError('Each component needs a distinct package')
    directory = Path(config.get('state_dir', ''))
    if not directory.is_absolute() or '..' in directory.parts or directory.is_symlink():
        raise ValueError('Invalid deployment-state directory')
    for key in ('current',):
        path = Path(config.get(key, ''))
        if not str(path) or path.is_absolute() or '..' in path.parts:
            raise ValueError('Invalid receipt path')
    for key in ('recovery_files', 'pending_globs'):
        if not isinstance(config.get(key), list):
            raise ValueError('Missing recovery constraints')
        for value in config[key]:
            path = Path(value)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Recovery paths must stay inside deployment state')
    if config.get('keep_previous') != 2 or config.get('minimum_age_hours') != 24:
        raise ValueError('This tested policy requires two prior releases and 24h discovery grace')
    return config


def configs(directory):
    result = {}
    packages = set()
    for path in sorted(directory.glob('*.json')):
        config = validate_config(read_json(path))
        if config['name'] in result or packages.intersection(config['repositories'].values()):
            raise ValueError('Duplicate app/package registration; cleanup stopped')
        result[config['name']] = config
        packages.update(config['repositories'].values())
    return result


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=60)
    if check and result.returncode:
        raise RuntimeError('Docker operation failed: ' + ' '.join(args[:3]))
    return result


def inspect_image(ref):
    result = docker('image', 'inspect', ref)
    data = json.loads(result.stdout)
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError('Invalid Docker image response')
    return data[0]


def validate_release(config, release):
    if not isinstance(release, dict) or not re.fullmatch(r'[0-9a-f]{40}', release.get('revision', '')):
        raise ValueError('Invalid successful release revision')
    images = release.get('images')
    if not isinstance(images, dict) or set(images) != set(config['repositories']):
        raise ValueError('Invalid successful image set')
    for field, package in config['repositories'].items():
        if not isinstance(images[field], str) or not re.fullmatch(re.escape(package) + r'@sha256:[0-9a-f]{64}', images[field]):
            raise ValueError('Release image is outside its exact registered package')
    return {'revision': release['revision'], 'images': images}


def receipt(config):
    data = read_json(Path(config['state_dir']) / config['current'])
    return validate_release(config, {'revision': data.get('revision'), 'images': {key: data.get(key) for key in config['repositories']}})


def key(release):
    return hashlib.sha256(json.dumps(release['images'], sort_keys=True).encode()).hexdigest()


def verified_images(config, release):
    for ref in release['images'].values():
        info = inspect_image(ref)
        labels = info.get('Config', {}).get('Labels') or {}
        if labels.get('org.opencontainers.image.source') != config['source'] or labels.get('org.opencontainers.image.revision') != release['revision']:
            raise ValueError('Image labels do not match the successful receipt')


def containers():
    ids = docker('ps', '-aq').stdout.split()
    return json.loads(docker('inspect', *ids).stdout) if ids else []


def verify_running(config, release, running):
    group = [item for item in running if item.get('Config', {}).get('Labels', {}).get('com.docker.compose.project') == config['project'] and item['State'].get('Running')]
    if not group or {item['Config']['Image'] for item in group} != set(release['images'].values()):
        raise ValueError('Running app does not match its committed successful image set')
    if any(item['State'].get('Health', {}).get('Status') != 'healthy' for item in group):
        raise ValueError('Application is not healthy; retain its images')


def protected_by_containers(running):
    refs, identities = set(), set()
    for item in running:
        refs.add(item['Config']['Image'])
        identities.add(item['Image'])
        # Resolve tagged/index aliases too; a failed reference resolution stops cleanup.
        identities.add(inspect_image(item['Config']['Image'])['Id'])
    return refs, identities


def pending(config):
    directory = Path(config['state_dir'])
    return any(list(directory.glob(pattern)) for pattern in config['pending_globs'])


@contextlib.contextmanager
def locked(path, wait_seconds=0):
    if path.is_symlink():
        raise ValueError('Refusing symbolic lock')
    with path.open('a') as stream:
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(0.1)
        try:
            yield True
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def history(config, path):
    data = read_json(path) if path.exists() else {'schema': 1, 'releases': [], 'first_seen': {}}
    if data.get('schema') != 1 or not isinstance(data.get('releases'), list) or not isinstance(data.get('first_seen'), dict):
        raise ValueError('Malformed retention ledger; no deletion')
    for item in data['releases']:
        validate_release(config, item)
    if len(data['releases']) > 3 or len({key(item) for item in data['releases']}) != len(data['releases']):
        raise ValueError('Retention ledger must contain up to three unique releases')
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0 for value in data['first_seen'].values()):
        raise ValueError('Invalid image observation timestamps')
    return data


def promote(data, release):
    if data['releases'] and key(data['releases'][0]) == key(release):
        if data['releases'][0]['revision'] != release['revision']:
            raise ValueError('Same image set claims a different revision')
        return False
    entry = dict(release, observed_at=now())
    data['releases'] = ([entry] + [item for item in data['releases'] if key(item) != key(release)])[:3]
    return True


def inventory(config):
    identities = set()
    for package in config['repositories'].values():
        rows = docker('image', 'ls', '--digests', '--no-trunc', '--format', '{{json .}}', package).stdout.splitlines()
        identities.update(json.loads(row)['ID'] for row in rows)
    return [inspect_image(identity) for identity in sorted(identities)]


def owned_refs(config, image):
    refs = set((image.get('RepoTags') or []) + (image.get('RepoDigests') or []))
    packages = set(config['repositories'].values())
    if not refs or any(not any(ref.startswith(package + '@') or ref.startswith(package + ':') for package in packages) for ref in refs):
        return None
    labels = image.get('Config', {}).get('Labels') or {}
    if labels.get('org.opencontainers.image.source') != config['source']:
        return None
    return refs


def recovery_refs(config):
    found = set()
    for relative in config['recovery_files']:
        path = Path(config['state_dir']) / relative
        if not path.exists():
            continue
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            raise ValueError('Unsafe recovery file; retain all images')
        content = path.read_text(encoding='utf-8')
        found.update(re.findall(REPOSITORY + r'@sha256:[0-9a-f]{64}', content))
    return found


def app_operation(config, action, state_dir, seed=None):
    report = {'app': config['name'], 'action': action, 'removed': [], 'eligible': [], 'retained': []}
    if (state_dir / (config['name'] + '.uncertain')).exists():
        return dict(report, status='history-uncertain-review-required')
    directory = Path(config['state_dir'])
    if not directory.is_dir():
        return dict(report, status='waiting-for-installation')
    with locked(directory / 'update.lock', 120 if action == 'observe' else 0) as acquired:
        if not acquired:
            return dict(report, status='deployment-busy')
        if pending(config):
            return dict(report, status='recovery-pending')
        if not (directory / config['current']).exists():
            return dict(report, status='waiting-for-first-release')
        path = state_dir / (config['name'] + '.json')
        data = history(config, path)
        current = receipt(config)
        if action == 'observe' and data['releases'] and key(data['releases'][0]) == key(current):
            if data['releases'][0]['revision'] != current['revision']:
                raise ValueError('Same image set claims a different revision')
            return dict(report, status='unchanged')
        verified_images(config, current)
        running = containers()
        verify_running(config, current, running)
        if action == 'seed':
            if data['releases']:
                raise ValueError('Seed would overwrite an established ledger')
            entries = seed.get('releases') if isinstance(seed, dict) else None
            if not isinstance(entries, list) or not 1 <= len(entries) <= 3:
                raise ValueError('Seed needs one to three proven releases, newest first')
            data['releases'] = [validate_release(config, entry) for entry in entries]
            if key(data['releases'][0]) != key(current) or len({key(item) for item in data['releases']}) != len(data['releases']):
                raise ValueError('Seed does not match current release or has duplicates')
            for entry in data['releases']:
                verified_images(config, entry)
            atomic_json(path, data)
            return dict(report, status='seeded', successful_releases=len(entries))
        promote(data, current)
        if action == 'observe':
            atomic_json(path, data)
            return dict(report, status='recorded', successful_releases=len(data['releases']))
        images = inventory(config)
        live_ids = {item['Id'] for item in images}
        data['first_seen'] = {identity: timestamp for identity, timestamp in data['first_seen'].items() if identity in live_ids}
        for identity in live_ids:
            data['first_seen'].setdefault(identity, now())
        # Persist successful history and observation times before deleting anything.
        if action == 'sweep':
            atomic_json(path, data)
        report['successful_releases'] = len(data['releases'])
        if len(data['releases']) < 3:
            return dict(report, status='building-three-release-history')
        keep = {ref for entry in data['releases'] for ref in entry['images'].values()} | recovery_refs(config)
        keep_ids = {inspect_image(ref)['Id'] for ref in keep}
        active_refs, active_ids = protected_by_containers(running)
        for image in images:
            identity = image['Id']
            refs = owned_refs(config, image)
            reason = None
            if refs is None:
                reason = 'unmanaged-alias-or-source'
            elif identity in keep_ids or refs.intersection(keep):
                reason = 'successful-history-or-recovery'
            elif identity in active_ids or refs.intersection(active_refs):
                reason = 'referenced-by-container'
            elif now() - data['first_seen'][identity] < 24 * 3600:
                reason = '24-hour-discovery-grace'
            if reason:
                report['retained'].append({'id': identity, 'reason': reason})
                continue
            report['eligible'].append({'id': identity, 'references': sorted(refs)})
            if action == 'plan':
                continue
            # Fresh all-container and alias checks under the app's deployment lock.
            latest_refs, latest_ids = protected_by_containers(containers())
            latest = inspect_image(identity)
            if latest['Id'] != identity or owned_refs(config, latest) != refs or identity in latest_ids or refs.intersection(latest_refs):
                report['retained'].append({'id': identity, 'reason': 'changed-during-cleanup'})
                continue
            if receipt(config) != current or pending(config):
                raise ValueError('Deployment state changed during cleanup')
            # No --force, container removal, volume/network deletion, or global prune.
            for ref in sorted(refs):
                exists = docker('image', 'inspect', ref, check=False)
                if exists.returncode:
                    continue
                if json.loads(exists.stdout)[0]['Id'] != identity:
                    raise ValueError('Image reference moved during cleanup')
                result = docker('image', 'rm', ref, check=False)
                if result.returncode:
                    raise RuntimeError('Docker retained a referenced image; stopped this app cleanup')
                report['removed'].append(ref)
        return dict(report, status='complete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['observe', 'seed', 'plan', 'sweep'])
    parser.add_argument('--app')
    parser.add_argument('--seed', type=Path)
    parser.add_argument('--config-dir', type=Path, default=CONFIG_DIR)
    parser.add_argument('--state-dir', type=Path, default=STATE_DIR)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run through the installed root-owned service or sudo')
    if args.action in ('observe', 'seed') and not args.app:
        parser.error('observe/seed require one registered --app')
    if args.action == 'seed' and not args.seed:
        parser.error('seed requires an operator-reviewed JSON file')
    if args.state_dir.is_symlink():
        parser.error('Refusing symbolic retention-state directory')
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    configured = configs(args.config_dir)
    if args.app and args.app not in configured:
        parser.error('App is not registered')
    # Observers change only one ledger while holding that app's deploy lock.
    # They do not wait behind unrelated apps in the global sweep queue.
    guard = contextlib.nullcontext(True) if args.action == 'observe' else locked(args.state_dir / 'retention.lock')
    with guard as acquired:
        if not acquired:
            print(json.dumps({'status': 'retention-busy'}))
            return 0
        results, failed = [], False
        for config in configured.values():
            if args.app and config['name'] != args.app:
                continue
            try:
                result = app_operation(config, args.action, args.state_dir, read_json(args.seed) if args.seed else None)
                results.append(result)
                if args.action == 'observe' and result['status'] not in ('recorded', 'unchanged', 'waiting-for-first-release', 'waiting-for-installation'):
                    failed = True
                    atomic_json(args.state_dir / (config['name'] + '.uncertain'), {'reason': result['status'], 'time': now()})
            except Exception as error:
                failed = True
                if args.action == 'observe':
                    atomic_json(args.state_dir / (config['name'] + '.uncertain'), {'reason': 'failed-successful-release-observation', 'time': now()})
                results.append({'app': config['name'], 'status': 'stopped', 'error': str(error)})
        print(json.dumps({'policy': 'current-plus-two-previous-successful-releases', 'results': results}, indent=2))
        return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
