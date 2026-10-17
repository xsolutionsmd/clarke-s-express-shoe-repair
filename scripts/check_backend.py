#!/usr/bin/env python3
"""Disposable Docker HTTP/replacement/restore drill; never uses installed volumes."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
PREFIX='clarke-s-express-shoe-repair-check-'+uuid.uuid4().hex[:10]
RUNTIME=PREFIX+':api'
TEST=PREFIX+':probe'
NETWORK=PREFIX+'-net'
VOLUME=PREFIX+'-data'
RESTORED=PREFIX+'-restore'
CONTAINER=PREFIX+'-app'
PROBE=PREFIX+'-probe'
COPY=PREFIX+'-copy'
REVISION=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()

def run(*args,capture=False,check=True):
    r=subprocess.run([str(a) for a in args],cwd=ROOT,text=True,capture_output=capture)
    if check and r.returncode:raise RuntimeError('Command failed: '+' '.join(str(a) for a in args[:4]))
    return r.stdout.strip() if capture else r.returncode

def inspect(kind,identity):
    return json.loads(run('docker',kind,'inspect',identity,capture=True))[0]

def start(volume):
    assert inspect('volume',volume)['Labels']['com.clarke.test-owner']==PREFIX
    run('docker','run','-d','--name',CONTAINER,'--label','com.clarke.test-owner='+PREFIX,
        '--network',NETWORK,'--network-alias','candidate','--memory','256m','--memory-swap','256m',
        '--pids-limit','100','--read-only','--tmpfs','/tmp:rw,size=32m','--security-opt','no-new-privileges:true',
        '--mount','type=volume,source='+volume+',target=/data',
        '--env','PUBLIC_ORIGIN=http://candidate:8080','--env','DEMO_MODE=true',RUNTIME,capture=True)
    deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        info=inspect('container',CONTAINER)
        if info['State']['Health']['Status']=='healthy':
            assert info['Config']['User']=='10001:10001' and info['HostConfig']['Memory']==268435456
            return
        if not info['State']['Running']:raise RuntimeError('API candidate exited; inspect sanitized application error.')
        time.sleep(.5)
    raise RuntimeError('API candidate did not become healthy.')

def stop():
    info=inspect('container',CONTAINER)
    assert info['Config']['Labels']['com.clarke.test-owner']==PREFIX
    run('docker','stop','--time','10',CONTAINER,capture=True)
    run('docker','rm',CONTAINER,capture=True)

def probe(volume,phase):
    run('docker','run','--rm','--name',PROBE,'--network',NETWORK,
        '--mount','type=volume,source='+volume+',target=/data',
        '--env','XS_E2E_ISOLATED='+PREFIX,'--env','APP_REVISION='+REVISION,
        TEST,'python','api_probe.py',phase)

try:
    for target,tag in [('backend-runtime',RUNTIME),('api-test',TEST)]:
        run('docker','build','--target',target,'--build-arg','APP_REVISION='+REVISION,
            '--build-arg','APP_SOURCE_URL=https://github.com/xsolutionsmd/clarke-s-express-shoe-repair','--tag',tag,'.')
    run('docker','run','--rm','--network','none','--read-only','--entrypoint','python',RUNTIME,
        '-c',"import pathlib,importlib.util; assert not any(pathlib.Path(p).exists() for p in ['/workspace/tests','/e2e','/probe','/opt/test-fixtures']); assert importlib.util.find_spec('pytest') is None; print('PASS: API runtime has no fixture/test packages.')")
    run('docker','network','create','--internal','--label','com.clarke.test-owner='+PREFIX,NETWORK,capture=True)
    for volume in (VOLUME,RESTORED):run('docker','volume','create','--label','com.clarke.test-owner='+PREFIX,volume,capture=True)
    start(VOLUME);probe(VOLUME,'create');stop()
    start(VOLUME);probe(VOLUME,'replacement');stop()
    run('docker','run','--rm','--name',COPY,'--network','none','--read-only','--user','0:0','--entrypoint','python',
        '--mount','type=volume,source='+VOLUME+',target=/source,readonly',
        '--mount','type=volume,source='+RESTORED+',target=/backup',RUNTIME,'-c',
        "import os,pathlib,shutil; shutil.copytree('/source','/backup',dirs_exist_ok=True); [os.chown(p,10001,10001) for p in pathlib.Path('/backup').rglob('*')]; os.chown('/backup',10001,10001)")
    start(RESTORED);probe(RESTORED,'restore');stop()
    print('PASS: isolated 256MB/100PID/read-only API container, genuine 12MP HEIC, replacement, full SQLite/uploads/keys restore. No provider network route.')
finally:
    # Exact task-created identities only, including failed runs; no global prune.
    for container in (CONTAINER,PROBE,COPY):
        r=subprocess.run(['docker','container','inspect',container],capture_output=True)
        if r.returncode==0:run('docker','rm','--force','--volumes',container,capture=True,check=False)
    for volume in (VOLUME,RESTORED):
        r=subprocess.run(['docker','volume','inspect',volume],capture_output=True,text=True)
        if r.returncode==0 and json.loads(r.stdout)[0].get('Labels',{}).get('com.clarke.test-owner')==PREFIX:
            run('docker','volume','rm',volume,capture=True,check=False)
    run('docker','network','rm',NETWORK,capture=True,check=False)
    for image in (RUNTIME,TEST):run('docker','image','rm',image,capture=True,check=False)
