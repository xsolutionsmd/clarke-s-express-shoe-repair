"""Exercise complete SQLite/upload/key backup and reject archive traversal."""
import importlib.util, io, json, sqlite3, tarfile, tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('backup',Path(__file__).resolve().parents[1]/'server/backup.py')
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)
calls=[];backup.compose=lambda root,*args:calls.append(args)
with tempfile.TemporaryDirectory() as td:
    p=Path(td);root=p/'root';state=p/'state';data=root/'data';data.mkdir(parents=True);state.mkdir()
    (data/'uploads').mkdir();(data/'uploads/photo.bin').write_bytes(b'synthetic upload')
    (data/'secret.key').write_text('synthetic-session');(data/'encryption.key').write_text('synthetic-encryption')
    with sqlite3.connect(data/'clarke.sqlite3') as db:db.execute('CREATE TABLE proof(value TEXT)');db.execute("INSERT INTO proof VALUES('persisted')")
    for n in backup.FILES:(root/n).write_text('synthetic '+n)
    (state/'current.json').write_text(json.dumps({'revision':'a'*40,'image':'synthetic'}))
    archive=backup.backup(root,state);restored=p/'restored';restored.mkdir();backup.unpack(archive,restored)
    assert (restored/'data/uploads/photo.bin').read_bytes()==b'synthetic upload'
    assert (restored/'data/encryption.key').read_text()=='synthetic-encryption'
    assert (restored/'runtime.env').read_text()=='synthetic runtime.env'
    with sqlite3.connect(restored/'data/clarke.sqlite3') as db:assert db.execute('SELECT value FROM proof').fetchone()[0]=='persisted'
    assert calls[0]==('stop','web') and calls[1][0]=='up'
    evil=p/'bad.tar.gz'
    with tarfile.open(evil,'w:gz') as t:
        m=tarfile.TarInfo('../escaped');m.size=1;t.addfile(m,io.BytesIO(b'x'))
    try:backup.unpack(evil,restored)
    except ValueError:pass
    else:raise AssertionError('Traversal accepted')
print('PASS complete SQLite, uploads, keys, runtime and release backup; safe extraction')
