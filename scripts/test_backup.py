"""Offline tests of actual restore orchestration; only host calls are mocked."""
import hashlib
import importlib.util
import io
import json
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SITE=Path(__file__).resolve().parents[1]
ENVIRONMENTS=('production','derek-dev','abdul-dev')
OLD='a'*40
NEW='b'*40


def load(environment):
    source=SITE/'server'/('' if environment=='production' else environment)/'backup.py'
    spec=importlib.util.spec_from_file_location('backup_'+environment,source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def model(module):
    return dict(name=module.SLUG,services={'web':{
        'image':'${APP_IMAGE:?Set the approved immutable application image}',
        'environment':{'APP_ENVIRONMENT':module.ENVIRONMENT},
        'env_file':[{'path':module.RUNTIME_PATH,'required':True}],
        'volumes':[{'type':'bind','source':module.DATA_PATH,'target':'/data'}],
        'read_only':True,'mem_limit':'256m','pids_limit':100}},
        networks={'proxy':{'external':True,'name':'xsolutions-proxy'}})


def fixture(root,state,module,revision=OLD):
    data=root/'data';data.mkdir(parents=True);state.mkdir()
    (data/'uploads').mkdir();(data/'uploads/photo.bin').write_bytes(b'synthetic upload')
    (data/'secret.key').write_text('synthetic-session');(data/'encryption.key').write_text('synthetic-encryption')
    with sqlite3.connect(data/'clarke.sqlite3') as db:
        db.execute('CREATE TABLE proof(value TEXT)');db.execute("INSERT INTO proof VALUES('persisted')")
        db.execute('CREATE TABLE app_meta(key TEXT PRIMARY KEY,value TEXT)')
        db.execute('INSERT INTO app_meta VALUES(?,?)',('environment_identity',module.ORIGIN))
    (root/'runtime.env').write_text('PUBLIC_ORIGIN='+module.ORIGIN+'\nDEMO_MODE=true\n')
    image=module.IMAGE_PACKAGE+'@sha256:'+('c' if revision==OLD else 'd')*64
    (root/'release.env').write_text('APP_IMAGE='+image+'\n')
    (root/'compose.yaml').write_text(json.dumps(model(module)))
    (state/'current.json').write_text(json.dumps({'revision':revision,'image':image}))


def pack(folder,path):
    with tarfile.open(path,'w:gz') as archive:
        for entry in folder.iterdir():archive.add(entry,arcname=entry.name)


def hashes(folder):
    return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.calls=[];self.https=[]

    def host(self,module,revision=OLD):
        def output(args,**kwargs):
            if args[:2]==['docker','compose']:
                self.assertIn('--no-env-resolution',args);self.assertIn('--no-interpolate',args)
                # JSON fixture is valid YAML; exercise the validator itself.
                return Path(args[args.index('-f')+1]).read_text()
            self.assertEqual(args[0],'curl');self.https.append(args)
            return json.dumps({'revision':revision})
        self.enterContext(patch.object(module,'compose',side_effect=lambda root,*args:self.calls.append(args)))
        self.enterContext(patch.object(module.subprocess,'check_output',side_effect=output))
        self.enterContext(patch.object(module.os,'chown'))

    def prepare(self,target='production',source=None):
        module=load(target);other=load(source or target)
        root=self.base/'target';state=self.base/'state';fixture(root,state,module,NEW)
        archive_root=self.base/'archive';archive_state=self.base/'archive-state'
        fixture(archive_root,archive_state,other)
        (archive_root/'current.json').write_bytes((archive_state/'current.json').read_bytes())
        return module,root,state,archive_root

    def reject(self,module,root,state,archive_root):
        self.host(module);archive=self.base/'bad.tar.gz';pack(archive_root,archive)
        original=hashes(root);state_before=hashes(state)
        with self.assertRaises(ValueError):module.restore(archive,root,state)
        self.assertEqual(self.calls,[],'Rejected restore stopped/touched the target')
        self.assertEqual(self.https,[])
        self.assertEqual(hashes(root),original);self.assertEqual(hashes(state),state_before)
        self.assertFalse((state/'transaction').exists());self.assertFalse((state/'backups').exists())

    def test_complete_older_revision_restore_preserves_recovery(self):
        module,root,state,source=self.prepare(self.target)
        (root/'data/uploads/photo.bin').write_bytes(b'new generation data')
        (root/'data/secret.key').write_text('new session key')
        (root/'data/encryption.key').write_text('new encryption key')
        previous=hashes(root);archive=self.base/'old.tar.gz';pack(source,archive);self.host(module)
        recovery=module.restore(archive,root,state)
        self.assertEqual((root/'data/uploads/photo.bin').read_bytes(),b'synthetic upload')
        self.assertEqual((root/'data/secret.key').read_text(),'synthetic-session')
        self.assertEqual((root/'data/encryption.key').read_text(),'synthetic-encryption')
        self.assertEqual(json.loads((state/'current.json').read_text())['revision'],OLD)
        with sqlite3.connect(root/'data/clarke.sqlite3') as db:self.assertEqual(db.execute('SELECT value FROM proof').fetchone()[0],'persisted')
        self.assertFalse((state/'transaction').exists())
        unpacked=self.base/'recovery';unpacked.mkdir();module.unpack(recovery,unpacked)
        self.assertEqual({k:v for k,v in hashes(unpacked).items() if k!='current.json'},previous)
        self.assertEqual(json.loads((unpacked/'current.json').read_text())['revision'],NEW)
        self.assertEqual(self.calls[0],('stop','web'));self.assertEqual(self.calls[2],('stop','web'))
        self.assertEqual(self.https[0][-1],module.ORIGIN+'/version.json')
        self.assertIn(module.ORIGIN.removeprefix('https://')+':443:127.0.0.1',self.https[0])

    def test_failed_https_keeps_guard_and_current_recovery(self):
        module,root,state,source=self.prepare(self.target);archive=self.base/'old.tar.gz';pack(source,archive)
        self.host(module,NEW)
        with self.assertRaises(RuntimeError):module.restore(archive,root,state)
        self.assertTrue((state/'transaction').exists());self.assertEqual(len(list((state/'backups').glob('*.tar.gz'))),1)
        self.assertEqual(json.loads((state/'current.json').read_text())['revision'],NEW)


def foreign_test(target,source):
    def test(self):self.reject(*self.prepare(target,source))
    return test


def mismatch_test(target,field):
    def test(self):
        module,root,state,source=self.prepare(target)
        config=json.loads((source/'compose.yaml').read_text());web=config['services']['web']
        if field=='origin':(source/'runtime.env').write_text('PUBLIC_ORIGIN=https://foreign.example.test\n')
        elif field=='runtime_environment':
            with (source/'runtime.env').open('a') as f:f.write('APP_ENVIRONMENT=foreign\n')
        elif field in ('database','database_missing_identity'):
            with sqlite3.connect(source/'data/clarke.sqlite3') as db:
                db.execute("UPDATE app_meta SET value='https://foreign.example.test'" if field=='database' else 'DELETE FROM app_meta')
        elif field=='image_package':
            image='ghcr.io/xsolutionsmd/foreign@sha256:'+'e'*64
            (source/'release.env').write_text('APP_IMAGE='+image+'\n')
            (source/'current.json').write_text(json.dumps({'revision':OLD,'image':image}))
        elif field=='release_mismatch':(source/'release.env').write_text('APP_IMAGE='+module.IMAGE_PACKAGE+'@sha256:'+'e'*64+'\n')
        elif field=='revision':(source/'current.json').write_text(json.dumps({'revision':'bad','image':module.IMAGE_PACKAGE+'@sha256:'+'c'*64}))
        elif field=='target_origin':(root/'runtime.env').write_text('PUBLIC_ORIGIN=https://foreign.example.test\n')
        elif field=='project':config['name']='foreign'
        elif field=='data_mount':web['volumes'][0]['source']='/opt/foreign/data'
        elif field=='runtime_mount':web['env_file'][0]['path']='/opt/foreign/runtime.env'
        elif field=='compose_environment':web['environment']['APP_ENVIRONMENT']='foreign'
        elif field=='compose_image':web['image']='ghcr.io/xsolutionsmd/foreign@sha256:'+'e'*64
        elif field=='extra_mount':web['volumes'].append({'type':'bind','source':'/','target':'/host'})
        elif field=='extra_service':config['services']['foreign']={'image':'foreign'}
        elif field=='policy':web['read_only']=False
        (source/'compose.yaml').write_text(json.dumps(config))
        self.reject(module,root,state,source)
    return test


# Independently load all branch copies. No installed /opt, volume or socket access.
for target in ENVIRONMENTS:
    cls=type('Restore_'+target.replace('-','_'),(RestoreTests,),{'target':target})
    for source in ENVIRONMENTS:
        if source!=target:setattr(cls,'test_foreign_'+source.replace('-','_'),foreign_test(target,source))
    for field in ('origin','runtime_environment','database','database_missing_identity','image_package','release_mismatch','revision','target_origin','project','data_mount','runtime_mount','compose_environment','compose_image','extra_mount','extra_service','policy'):
        setattr(cls,'test_reject_'+field,mismatch_test(target,field))
    globals()[cls.__name__]=cls
del cls


class ExtractionTests(unittest.TestCase):
    def test_traversal_and_symlink_rejected(self):
        module=load('production')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for symlink in (False,True):
                archive=p/'bad.tar.gz'
                with tarfile.open(archive,'w:gz') as tar:
                    member=tarfile.TarInfo('data/evil' if symlink else '../escaped')
                    if symlink:member.type=tarfile.SYMTYPE;member.linkname='/etc/passwd';tar.addfile(member)
                    else:member.size=1;tar.addfile(member,io.BytesIO(b'x'))
                with self.assertRaises(ValueError):module.unpack(archive,p/'out')
                self.assertFalse((p.parent/'escaped').exists())


if __name__=='__main__':
    suite=unittest.TestSuite()
    for name,value in list(globals().items()):
        if name.startswith('Restore_') or name=='ExtractionTests':suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(value))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(not result.wasSuccessful())
