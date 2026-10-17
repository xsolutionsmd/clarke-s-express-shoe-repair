"""Branch-bound whole-repository context: Graft graph plus bounded text retrieval."""
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'app-launchpad-graft:0.18.0-node22.22.0'

def run(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd or ROOT, text=True, encoding='utf-8').strip()

def git(*args):
    return run(['git', *args])

def configured_refs():
    branches = None
    company = ROOT / 'xsolutions.json'
    workflow = ROOT / 'app-workflow.json'
    if company.is_file():
        environments = json.loads(company.read_text(encoding='utf-8-sig')).get('environments')
        if environments is not None:
            if not isinstance(environments, list) or any(not isinstance(env, dict) for env in environments):
                raise ValueError('xsolutions.json environments must list branch objects')
            branches = [env.get('branch') for env in environments]
    if branches is None and workflow.is_file():
        branches = json.loads(workflow.read_text(encoding='utf-8-sig')).get('branches')
    if branches is None:
        branches = ['dev', 'main']
    if not isinstance(branches, list) or not branches or any(not isinstance(branch, str) or not branch for branch in branches) or 'main' not in branches:
        raise ValueError('Configured branches must be a nonempty list of branch names including main')
    for branch in branches:
        git('check-ref-format', 'refs/heads/' + branch)
    return tuple(dict.fromkeys(branches))

def identity(ref, feature=False):
    config = json.loads((ROOT / 'tools/graft/context.json').read_text(encoding='utf-8-sig'))
    patterns = config.get('sourcePatterns')
    if not isinstance(patterns, list) or not patterns or any(not isinstance(p, str) or not p or (p != '**' and '/' not in p) or p.startswith('/') or '..' in Path(p).parts for p in patterns):
        raise ValueError('sourcePatterns must be a nonempty list of repository-relative patterns')
    repo = config['repository']
    remote = git('remote', 'get-url', 'origin')
    if remote not in (f'https://github.com/{repo}.git', f'git@github.com:{repo}.git'):
        raise ValueError('Unexpected origin repository; refusing context access')
    if git('rev-parse', '--show-toplevel').replace('\\', '/') != ROOT.as_posix():
        raise ValueError('Launcher must belong to the checkout root')
    refs = configured_refs()
    if ref not in refs:
        raise ValueError(f'Expected a configured ref: {", ".join(refs)}')
    branch = git('branch', '--show-current')
    if feature and (ref == 'main' or branch in ('', 'main')):
        raise ValueError('Feature context requires an attached development branch, never main')
    if (not feature or branch in refs) and branch != ref:
        raise ValueError(f'Expected branch {ref}; got {branch or "detached HEAD"}')
    dirty = bool(git('status', '--porcelain', '--untracked-files=all'))
    if ref == 'main' and dirty:
        raise ValueError('Production context requires a clean main checkout')
    omitted = git('ls-files', '--others', '--exclude-standard').splitlines()
    key = quote(ref, safe='')
    if feature:
        key += '-feature-' + hashlib.sha256(branch.encode()).hexdigest()[:12]
    return config, dict(repository=repo, ref=ref, branch=branch, feature=feature, cacheKey=key, root=str(ROOT), revision=git('rev-parse', 'HEAD'), dirty=dirty, omittedUntracked=omitted)

TEXT_EXTENSIONS = {'.js', '.cjs', '.mjs', '.jsx', '.ts', '.tsx', '.go', '.py', '.sh', '.ps1', '.bat', '.html', '.css', '.md', '.json', '.yaml', '.yml', '.toml', '.txt', '.sql', '.mod', '.sum', '.xml', '.svg', '.service', '.timer'}
TEXT_NAMES = {'Dockerfile', 'Caddyfile', 'Caddyfile.local', 'website', '.dockerignore', '.gitignore', '.gitattributes', 'LICENSE', 'Makefile'}
PRIVATE_DIRS = {'node_modules', 'vendor', '.graft-context', '.git', '.local', '.openai', '.codex', '.claude', 'backups', 'private', 'data', 'runtime', 'logs', 'models', 'recordings', 'transcripts', '__pycache__'}
AUTHORED_RUNTIME_FILES = {'runtime/nginx.conf', 'runtime/vite.config.mjs'}
MAX_FILE_BYTES = 1_000_000

def eligible(p):
    # Only these two authored configs may bypass the root runtime directory rule.
    authored_runtime = p.as_posix() in AUTHORED_RUNTIME_FILES
    private_parts = p.parts[1:] if authored_runtime else p.parts
    if p.parts[0].lower() == 'graft' or any(part.lower() in PRIVATE_DIRS for part in private_parts):
        return False
    if any(part.startswith('.') and part not in ('.github', '.devcontainer') and part not in TEXT_NAMES for part in p.parts):
        return False
    credential = p.stem.lower().replace('_', '-').replace('.', '-')
    if credential in ('google-client', 'operator-access', 'credential', 'credentials', 'secret', 'secrets', 'token', 'tokens', 'oauth-token', 'oauth-tokens', 'client-secret', 'client-secrets', 'service-account', 'service-account-key') and p.suffix.lower() in ('.json', '.yaml', '.yml', '.toml', '.txt'):
        return False
    return authored_runtime or p.suffix.lower() in TEXT_EXTENSIONS or p.name in TEXT_NAMES or p.name.startswith(('Dockerfile.', 'Caddyfile.'))

def read_source(source):
    if not source.is_file() or source.is_symlink() or source.resolve() != source.absolute() or not source.resolve().is_relative_to(ROOT):
        return None
    if source.stat().st_size > MAX_FILE_BYTES:
        return None
    with source.open('rb') as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES or b'\0' in data:
        return None
    try:
        data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return None
    return data

def inventory(config):
    paths = []
    for line in git('ls-files', '-s', '-z').split('\0'):
        if not line:
            continue
        entry, name = line.split('\t', 1)
        if entry.split()[0] != '100644' and entry.split()[0] != '100755':
            continue  # No symlinks or submodules.
        p = Path(name)
        if not any(pattern == '**' or (len(p.parts) == len(Path(pattern).parts) and all(fnmatch.fnmatchcase(part, rule) for part, rule in zip(p.parts, Path(pattern).parts))) for pattern in config['sourcePatterns']):
            continue
        if not eligible(p):
            continue
        source = ROOT / p
        if read_source(source) is not None:
            paths.append(name)
    return sorted(paths)

def snapshot(config, info):
    cache = ROOT / '.graft-context' / info['cacheKey']
    if cache.resolve() != cache.absolute():
        raise ValueError('Cache must not resolve through a symlink')
    cache.mkdir(parents=True, exist_ok=True)
    stamp = cache / 'identity.json'
    if stamp.exists():
        old = json.loads(stamp.read_text())
        if any(old.get(k) != info[k] for k in ('repository', 'ref', 'branch', 'root')):
            raise ValueError('Cache identity mismatch; remove this checkout cache explicitly')
    src = cache / 'source'
    if src.resolve() != src.absolute():
        raise ValueError('Source snapshot must not resolve through a symlink')
    src.mkdir(exist_ok=True)
    names = inventory(config)
    wanted = {src / name for name in names}
    for path in src.rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink in source snapshot')
        if path.is_file() and path not in wanted:
            path.unlink()
    hashes = {}
    for name in names:
        data = read_source(ROOT / name)
        if data is None:
            raise ValueError('Source changed or became ineligible during snapshot; retry')
        dest = src / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.read_bytes() != data:
            dest.write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    stamp.write_text(json.dumps(dict(info, files=hashes), indent=2) + '\n')
    verify_snapshot(config, info, cache)
    return cache

def verify_snapshot(config, info, cache):
    current_config, current = identity(info['ref'], info['feature'])
    if current_config != config or any(current[k] != info[k] for k in ('revision', 'branch')):
        raise ValueError('Checkout identity changed while reading source; retry')
    stamp = json.loads((cache / 'identity.json').read_text())
    actual = {}
    for name in inventory(config):
        data = read_source(ROOT/name)
        if data is None:
            raise ValueError('Source changed while validating snapshot; retry')
        actual[name] = hashlib.sha256(data).hexdigest()
    if actual != stamp['files']:
        raise ValueError('Source changed while building context; retry')

def tool_fingerprint():
    return hashlib.sha256(b''.join((ROOT/'tools/graft'/p).read_bytes() for p in ('Dockerfile', 'package.json', 'package-lock.json'))).hexdigest()

def setup():
    subprocess.run(['docker', 'build', '-t', IMAGE, str(ROOT / 'tools/graft')], check=True)
    image_id = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', IMAGE])
    versions = run(['docker', 'run', '--rm', '--network=none', '--entrypoint', 'node', image_id, '-p',
                    'process.version + " " + require("/opt/graft/node_modules/@nanonets/graft/package.json").version'])
    if versions != 'v22.22.0 0.18.0':
        raise ValueError('Unexpected runtime/package version')
    cache = ROOT / '.graft-context'
    if cache.resolve() != cache.absolute():
        raise ValueError('Cache must not resolve through a symlink')
    cache.mkdir(exist_ok=True)
    (cache/'runtime.json').write_text(json.dumps({'imageId':image_id, 'versions':versions, 'fingerprint':tool_fingerprint()}, indent=2))
    print(versions + ' ' + image_id)

def container(cache, args):
    receipt = ROOT / '.graft-context/runtime.json'
    if not receipt.exists():
        raise ValueError('Run setup in this checkout first')
    runtime = json.loads(receipt.read_text())
    if runtime['fingerprint'] != tool_fingerprint() or runtime['versions'] != 'v22.22.0 0.18.0':
        raise ValueError('Tooling changed; rerun setup')
    return ['docker', 'run', '--rm', '--network=none', '--read-only', '--tmpfs', '/tmp',
            '-e', 'HOME=/tmp', '-e', 'DO_NOT_TRACK=1', '-e', 'GRAFT_NO_SEED=1',
            '-e', 'GRAFT_NO_GITIGNORE=1', '-e', 'GRAFT_NO_IGNORE=1',
            '--mount', f'type=bind,source={cache},target=/context',
            '-w', '/context', runtime['imageId'], *args]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', required=True, choices=configured_refs())
    parser.add_argument('--feature', action='store_true', help='Explicit feature checkout; --ref selects its configured preview base for remote reads')
    parser.add_argument('--start-line', type=int, default=1)
    parser.add_argument('action', choices=['setup', 'status', 'build', 'ask', 'callers', 'api', 'search', 'read', 'remote'])
    parser.add_argument('query', nargs='?')
    args = parser.parse_args()
    config, info = identity(args.ref, args.feature)
    if args.action == 'setup':
        setup()
        return
    if args.action == 'status':
        files = inventory(config)
        print(json.dumps(dict(info, files=files, excludedTracked=sorted(set(git('ls-files').splitlines())-set(files))), indent=2))
        return
    if args.action == 'remote':
        endpoint = f'repos/{info["repository"]}/git/ref/heads/{quote(info["ref"], safe="/")}'
        if args.query:
            if args.query.startswith('/') or '..' in Path(args.query).parts:
                raise ValueError('Expected a repository-relative file path')
            endpoint = f'repos/{info["repository"]}/contents/{quote(args.query, safe="/")}?ref={quote(info["ref"], safe="")}'
        print(run(['gh', 'api', '--method', 'GET', endpoint]))
        return
    if args.action in ('ask', 'callers', 'api', 'search', 'read') and (not args.query or args.query.startswith('-')):
        raise ValueError('Provide a query or source file path')
    lock_dir = ROOT / '.graft-context'
    if lock_dir.resolve() != lock_dir.absolute():
        raise ValueError('Cache must not resolve through a symlink')
    lock_dir.mkdir(exist_ok=True)
    lock = lock_dir / (info['cacheKey'] + '.lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError('Context already in use; remove stale lock only after confirming no query is running')
    try:
        os.close(fd)
        execute(args, config, info)
    finally:
        lock.unlink()

def execute(args, config, info):
    cache = snapshot(config, info)
    if args.action in ('search', 'read'):
        text_context(args, cache)
        verify_snapshot(config, info, cache)
        return
    # Explicit build before every query: no hidden upkeep/init, paid mode or arbitrary CLI args.
    subprocess.run(container(cache, ['build', '/context', '--only-dir', 'source', '--include-dir', 'dist', '--no-gitignore', '--no-ignore']), check=True, stdout=sys.stderr)
    verify_snapshot(config, info, cache)
    commands = {
        'ask': ['ask', args.query, '/context', '--limit', '5', '--source', '--no-refresh'],
        'callers': ['callers', args.query, '/context', '--depth', '1', '--no-refresh'],
        'api': ['skeleton', 'source/' + (args.query or ''), '/context', '--no-refresh'],
    }
    if args.action in commands:
        subprocess.run(container(cache, commands[args.action]), check=True)
        if args.action == 'ask':
            print('\nRepository text matches (includes Docker/CI/docs; use search/read to expand):')
            text_context(args, cache)
    else:
        print(json.dumps(info, indent=2))

def text_context(args, cache):
    names = json.loads((cache/'identity.json').read_text())['files']
    if args.action == 'read':
        if args.query not in names or args.start_line < 1:
            raise ValueError('Read requires an inventoried repository-relative path and a positive start line')
        lines = (cache/'source'/args.query).read_text(encoding='utf-8-sig').splitlines()
        output = '\n'.join(f'{args.query}:{i+1}: {line}' for i,line in enumerate(lines) if args.start_line <= i+1 < args.start_line+120)
        print(output[:12000])
        print(f'\n[bounded read: at most 120 lines/12000 characters; file has {len(lines)} lines]')
        return
    hits=[]
    for name in names:
        if args.query.casefold() in name.casefold():
            hits.append(f'{name}: path match')
        for number,line in enumerate((cache/'source'/name).read_text(encoding='utf-8-sig').splitlines(),1):
            if args.query.casefold() in line.casefold():
                hits.append(f'{name}:{number}: {line[:300]}')
            if len(hits)>=40: break
        if len(hits)>=40: break
    print(('\n'.join(hits) or 'No literal text matches. Try a filename or shorter literal with search.')[:12000])
    print('[bounded text search: at most 40 matches/12000 characters; verify surrounding lines with read]')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
