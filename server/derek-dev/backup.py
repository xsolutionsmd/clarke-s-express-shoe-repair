#!/usr/bin/env python3
"""Quiesced complete data/config backups; matched restore under the deployment lock."""
import argparse, fcntl, json, os, re, shutil, sqlite3, subprocess, tarfile, tempfile, time
from pathlib import Path
SLUG = 'clarke-s-express-shoe-repair-derek-dev'
ENVIRONMENT = 'derek-dev'
# Installed root-owned target policy, NEVER read from the recovery archive.
ORIGIN = 'https://'+SLUG+'.xsolutionsmd.com'
IMAGE_PACKAGE = 'ghcr.io/xsolutionsmd/'+SLUG
DATA_PATH = '/opt/'+SLUG+'/data'
RUNTIME_PATH = '/opt/'+SLUG+'/runtime.env'
FILES = ('runtime.env', 'release.env', 'compose.yaml')

def compose(root, *args):
    subprocess.run(['docker','compose','--project-name',SLUG,'--env-file',str(root/'release.env'),
                    '-f',str(root/'compose.yaml'),*args],check=True,stdout=subprocess.DEVNULL)

def validate_data(data):
    for p in data.rglob('*'):
        if p.is_symlink(): raise ValueError('Data symlinks are not supported')
        if p.is_file() and p.suffix in ('.sqlite3','.sqlite','.db'):
            with sqlite3.connect(p) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Database integrity check failed')


def env_values(path):
    """Read the generated literal env format; never evaluate shell/interpolation."""
    values={}
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        key,sep,value=line.partition('=')
        if not sep or not re.fullmatch('[A-Z][A-Z0-9_]*',key) or key in values:
            raise ValueError('Invalid or duplicate environment setting')
        if value[:1] in ('"',"'"):
            if len(value)<2 or value[-1]!=value[0]:raise ValueError('Invalid quoted environment setting')
            value=value[1:-1]
        values[key]=value
    return values


def compose_model(path):
    # Config-only: no daemon mutation, interpolation or env_file loading. In
    # particular, do not load the target's secrets while reading an archive.
    env={k:os.environ[k] for k in ('PATH','HOME','DOCKER_HOST','DOCKER_CONFIG') if k in os.environ}
    raw=subprocess.check_output(['docker','compose','--env-file','/dev/null','-f',str(path),
        'config','--format','json','--no-env-resolution','--no-interpolate','--no-path-resolution'],
        env=env,stderr=subprocess.DEVNULL,text=True)
    return json.loads(raw)


def validate_identity(folder,manifest_path,model):
    runtime=env_values(folder/'runtime.env');release=env_values(folder/'release.env')
    if runtime.get('PUBLIC_ORIGIN')!=ORIGIN or runtime.get('APP_ENVIRONMENT',ENVIRONMENT)!=ENVIRONMENT:
        raise ValueError('Restore environment/origin does not match this target')
    if runtime.get('DATA_DIR','/data')!='/data':raise ValueError('Unexpected application data directory')
    manifest=json.loads(manifest_path.read_text())
    if set(manifest)!={'revision','image'} or not isinstance(manifest['revision'],str) or not re.fullmatch('[0-9a-f]{40}',manifest['revision']):
        raise ValueError('Invalid matched release identity')
    image=manifest['image']
    if not isinstance(image,str) or not re.fullmatch(re.escape(IMAGE_PACKAGE)+r'@sha256:[0-9a-f]{64}',image) or release!={'APP_IMAGE':image}:
        raise ValueError('Restore image package or matched release disagrees')
    if model.get('name')!=SLUG or set(model.get('services',{}))!={'web'}:
        raise ValueError('Restore Compose project/services disagree')
    web=model['services']['web']
    if web.get('environment')!={'APP_ENVIRONMENT':ENVIRONMENT}:
        raise ValueError('Restore Compose environment disagrees')
    if web.get('env_file')!=[{'path':RUNTIME_PATH,'required':True}]:
        raise ValueError('Restore runtime mount disagrees')
    mounts=web.get('volumes',[])
    if len(mounts)!=1 or mounts[0].get('type')!='bind' or mounts[0].get('source')!=DATA_PATH or mounts[0].get('target')!='/data' or mounts[0].get('read_only',False):
        raise ValueError('Restore data mount disagrees')
    if web.get('image') not in (image,'${APP_IMAGE:?Set the approved immutable application image}'):
        raise ValueError('Restore Compose image disagrees')
    # Ignore only the concrete digest while comparing the approved Compose policy;
    # reverting an older revision of the SAME package remains supported.
    web['image']=IMAGE_PACKAGE
    return manifest


def validate_database_identity(data):
    path=data/'clarke.sqlite3'
    if not path.exists():
        # Pre-application placeholder snapshots have no functional database.
        return
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        try:identity=db.execute("SELECT value FROM app_meta WHERE key='environment_identity'").fetchone()
        except sqlite3.DatabaseError:raise ValueError('Missing database environment identity') from None
    if not identity or identity[0]!=ORIGIN:
        raise ValueError('Restore database belongs to another environment')


def preflight_restore(folder,root,state):
    # Validate both sets against the installed target policy. The current target
    # Compose configuration is trusted; the archive cannot extend its privileges.
    trusted=compose_model(root/'compose.yaml')
    validate_identity(root,state/'current.json',trusted)
    archived=compose_model(folder/'compose.yaml')
    manifest=validate_identity(folder,folder/'current.json',archived)
    if archived!=trusted:raise ValueError('Restore Compose policy differs from the trusted target')
    validate_database_identity(folder/'data')
    return manifest['revision']

def backup(root, state):
    with tempfile.TemporaryDirectory(prefix='backup-',dir=state) as tmp:
        tmp=Path(tmp)
        compose(root,'stop','web')
        try:
            validate_data(root/'data')
            shutil.copytree(root/'data',tmp/'data')
            for name in FILES: shutil.copy2(root/name,tmp/name)
            shutil.copy2(state/'current.json',tmp/'current.json')
        finally:
            compose(root,'up','-d','--no-build','--wait','--wait-timeout','90')
        dest=state/'backups';dest.mkdir(exist_ok=True,mode=0o700)
        target=dest/('daily-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+str(time.time_ns())+'.tar.gz')
        with tarfile.open(target,'w:gz') as archive:
            for p in tmp.iterdir(): archive.add(p,arcname=p.name)
        target.chmod(0o600)
        with target.open('rb') as f: os.fsync(f.fileno())
        return target

def unpack(archive, destination):
    with tarfile.open(archive,'r:gz') as t:
        for m in t.getmembers():
            p=Path(m.name)
            if p.is_absolute() or '..' in p.parts or m.issym() or m.islnk() or not (m.isdir() or m.isfile()):
                raise ValueError('Unsafe backup member')
        t.extractall(destination,filter='data')
    for name in (*FILES,'current.json'):
        if not (destination/name).is_file(): raise ValueError('Incomplete matched backup')
    if not (destination/'data').is_dir(): raise ValueError('Missing data')
    validate_data(destination/'data')

def restore(archive, root, state):
    # Never discard the current data when restoring a prior generation.
    with tempfile.TemporaryDirectory(prefix='restore-',dir=state) as tmp:
        tmp=Path(tmp);unpack(archive,tmp)
        # Fail BEFORE backup() (which stops the service), the guard, or any target
        # data/config changes. Only isolated archive staging has happened so far.
        expected=preflight_restore(tmp,root,state)
        recovery=backup(root,state)
        (state/'transaction').write_text('Manual restore in progress; recovery archive: '+str(recovery)+'\n')
        compose(root,'stop','web')
        try:
            for p in (root/'data').iterdir():
                if p.is_symlink(): raise ValueError('Refuse symlink in data')
                if p.is_dir(): shutil.rmtree(p)
                else: p.unlink()
            shutil.copytree(tmp/'data',root/'data',dirs_exist_ok=True)
            for p in (root/'data',*(root/'data').rglob('*')):os.chown(p,10001,10001)
            for name in FILES:
                shutil.copy2(tmp/name,root/name);os.chown(root/name,0,0);(root/name).chmod(0o600)
            compose(root,'up','-d','--no-build','--wait','--wait-timeout','90')
            host=ORIGIN.removeprefix('https://')
            actual=json.loads(subprocess.check_output(['curl','-fsS','--max-time','15','--resolve',host+':443:127.0.0.1',ORIGIN+'/version.json'],text=True))['revision']
            if actual != expected: raise ValueError('Restored HTTPS revision mismatch')
            shutil.copy2(tmp/'current.json',state/'current.json');(state/'current.json').chmod(0o600)
            (state/'transaction').unlink()
        except BaseException:
            raise RuntimeError('Restore failed; timer must stay paused. Recovery archive: '+str(recovery)) from None
        return recovery

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--restore',type=Path);args=parser.parse_args()
    if os.geteuid()!=0: raise SystemExit('Run as root')
    os.umask(0o077);root=Path('/opt')/SLUG;state=Path('/var/lib')/(SLUG+'-deploy')
    for p in (root,state,root/'data'):
        if p.is_symlink() or not p.is_dir(): raise SystemExit('Unsafe or missing directory')
    with (state/'update.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (state/'transaction').exists(): raise SystemExit('Deployment recovery is pending; preserve evidence first')
        if not (state/'current.json').is_file(): print('No initialized release to back up yet');return
        if args.restore:
            if subprocess.run(['systemctl','is-active','--quiet',SLUG+'-update.timer']).returncode==0:
                raise SystemExit('Stop the update timer before restore')
            print('Restored; preserved prior data at',restore(args.restore.resolve(strict=True),root,state))
        else: print(backup(root,state))
if __name__=='__main__':main()
