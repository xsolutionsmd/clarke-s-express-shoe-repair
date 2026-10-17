"""Transactional SQLite, compatible persistent keys and checksummed migrations."""
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
from cryptography.fernet import Fernet
from flask import current_app
from itsdangerous import URLSafeTimedSerializer
from .core import now

class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def connect():
    c=sqlite3.connect(Path(current_app.config['DATA_DIR'])/'clarke.sqlite3',timeout=5,factory=ClosingConnection)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=5000')
    c.execute('PRAGMA synchronous=FULL')
    return c

@contextlib.contextmanager
def transaction():
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        yield c

def settings(c):
    return json.loads(c.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])

def save_settings(c,values,pending=None):
    c.execute('UPDATE settings SET data=?,pending_retention=?,version=version+1,updated_at=? WHERE id=1',(json.dumps(values),json.dumps(pending) if pending else None,now()))

def key_file(folder,name,configured,generator):
    path=folder/name
    if path.is_symlink():
        raise RuntimeError('Unsafe application key path.')
    supplied=configured.encode() if configured else None
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream: existing=stream.read(4096).strip()
        if supplied and not secrets.compare_digest(existing,supplied):
            raise RuntimeError('Application key configuration disagrees.')
        if not existing: raise RuntimeError('Application key is empty.')
        return existing
    value=supplied or generator()
    with os.fdopen(fd,'wb') as stream:
        stream.write(value);stream.flush();os.fsync(stream.fileno())
    return value

def initialize(app):
    folder=Path(app.config['DATA_DIR'])
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if folder.is_symlink(): raise RuntimeError('Unsafe application data path.')
    app.secret_key=key_file(folder,'secret.key',app.config.get('SESSION_SECRET'),lambda:secrets.token_hex(48).encode())
    app.extensions['cipher']=Fernet(key_file(folder,'encryption.key',app.config.get('ENCRYPTION_KEY'),Fernet.generate_key))
    app.extensions['sessions']=URLSafeTimedSerializer(app.secret_key,salt='clarke-session-v1')
    app.extensions['cursor']=URLSafeTimedSerializer(app.secret_key,salt='clarke-cursor-v1')
    for child in ('uploads','uploads/quarantine','uploads/sanitized'):
        p=folder/child
        p.mkdir(exist_ok=True,mode=0o700)
        if p.is_symlink():raise RuntimeError('Unsafe upload path.')
    with open(folder/'migration.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,checksum TEXT NOT NULL,applied_at INTEGER NOT NULL)')
            migrations=Path(__file__).resolve().parents[1]/'migrations'
            for path in sorted(migrations.glob('[0-9][0-9][0-9]_*')):
                if path.suffix not in ('.sql','.py'):continue
                number=int(path.name[:3]);content=path.read_bytes();checksum=hashlib.sha256(content).hexdigest()
                existing=c.execute('SELECT checksum FROM schema_migrations WHERE version=?',(number,)).fetchone()
                if existing:
                    if existing[0]!=checksum:raise RuntimeError('Applied migration checksum changed.')
                    continue
                c.execute('BEGIN IMMEDIATE')
                try:
                    if path.suffix=='.sql':
                        statement=''
                        for line in content.decode().splitlines(True):
                            statement+=line
                            if sqlite3.complete_statement(statement):c.execute(statement);statement=''
                        if statement.strip():raise RuntimeError('Incomplete migration.')
                    else:
                        spec=importlib.util.spec_from_file_location('defaults_migration',path)
                        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                        module.apply(c,app.config,now())
                    c.execute('INSERT INTO schema_migrations VALUES(?,?,?)',(number,checksum,now()));c.commit()
                except Exception:
                    c.rollback();raise
            # Fail readiness rather than silently discard data encrypted under another key.
            for table,column in [('integration_secrets','ciphertext'),('requests','status_token_cipher'),('outbox','body_cipher')]:
                for r in c.execute(f'SELECT {column} FROM {table} WHERE {column} IS NOT NULL'):
                    app.extensions['cipher'].decrypt(r[0].encode())
