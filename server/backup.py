#!/usr/bin/env python3
"""Quiesced complete data/config backups; matched restore under the deployment lock."""
import argparse, fcntl, json, os, shutil, sqlite3, subprocess, tarfile, tempfile, time
from pathlib import Path
SLUG = 'clarke-s-express-shoe-repair'
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
        expected=json.loads((tmp/'current.json').read_text())['revision']
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
            origin=next(x.split('=',1)[1] for x in (root/'runtime.env').read_text().splitlines() if x.startswith('PUBLIC_ORIGIN='))
            actual=json.loads(subprocess.check_output(['curl','-fsS','--max-time','15',origin+'/version.json'],text=True))['revision']
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
