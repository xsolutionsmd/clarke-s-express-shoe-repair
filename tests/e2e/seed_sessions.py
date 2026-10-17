"""E2E-only direct SQLite fixture. This file is never in the runtime image.

The launcher verifies the candidate container and volume's Compose ownership before
mounting it here. No network authentication bypass or real provider token is used.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
import uuid
from itsdangerous import URLSafeTimedSerializer

DATA=Path('/data')

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def database():
    if not os.getenv('XS_E2E_ISOLATED','').startswith('clarke-s-express-shoe-repair-check-'):
        raise RuntimeError('Refusing fixture access without an isolated candidate identity.')
    c=sqlite3.connect(DATA/'clarke.sqlite3',timeout=5,factory=ClosingConnection);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
    if c.execute("SELECT value FROM app_meta WHERE key='environment_identity'").fetchone()[0]!='http://candidate:8080':
        c.close();raise RuntimeError('Refusing a non-candidate database.')
    return c

def seed(role='admin',expired=False,member_id=None):
    stamp=int(time.time()*1000);ident=member_id or str(uuid.uuid4());sid=secrets.token_urlsafe(32)
    secret=(DATA/'secret.key').read_bytes().strip();csrf_key=hmac.new(secret,b'clarke-csrf-v1',hashlib.sha256).digest()
    csrf=base64.urlsafe_b64encode(hmac.new(csrf_key,sid.encode(),hashlib.sha256).digest()).decode().rstrip('=')
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        if member_id is None:
            c.execute('INSERT INTO members VALUES(?,?,?,?,1,1,?,?,?)',(ident,role+'-'+ident[:8]+'@example.test','synthetic-e2e-'+ident,role,stamp,stamp,stamp))
        member=c.execute('SELECT * FROM members WHERE id=? AND active=1 AND google_sub IS NOT NULL',(ident,)).fetchone()
        assert member and member['role']==role, 'Restoration requires the same active fixture member.'
        c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,NULL,?)',(hashlib.sha256(sid.encode()).hexdigest(),hashlib.sha256(csrf.encode()).hexdigest(),ident,member['version'],stamp,stamp,stamp-1 if expired else stamp+43200000,stamp-1 if expired else stamp+7200000,'google'))
    return dict(memberId=ident,csrf=csrf,cookie=dict(name='clarke_session',value=URLSafeTimedSerializer(secret,salt='clarke-session-v1').dumps({'sid':sid}),url=os.environ.get('BASE_URL','http://candidate:8080'),httpOnly=True,secure=False,sameSite='Lax'))

def reset_business():
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        data=json.loads(c.execute('SELECT data FROM settings WHERE id=1').fetchone()[0]);data.update(intakeAccepting=True,intakePauseMessage=None,notificationEmails=['alerts@example.test'],emailDeliveryEnabled=False)
        c.execute('UPDATE settings SET data=?,pending_retention=NULL,version=version+1',(json.dumps(data),))
        c.execute('UPDATE notices SET deleted_at=? WHERE deleted_at IS NULL',(int(time.time()*1000),))
        c.execute('DELETE FROM rate_limits')
        c.execute('UPDATE requests SET is_synthetic=1')
        days=[None,None]+[dict(open='09:00',close='17:00') for _ in range(4)]+[dict(open='10:00',close='13:00')]
        c.execute('UPDATE hours SET days=?,version=version+1',(json.dumps(days),))

def expire(member):
    with database() as c:c.execute('UPDATE sessions SET idle_expires_at=? WHERE member_id=?',(int(time.time()*1000)-1,member))

def exports():
    result={role:seed(role) for role in ('admin','viewer')}
    (DATA/'e2e-sessions.json').write_text(json.dumps(result),encoding='utf-8')
    os.chmod(DATA/'e2e-sessions.json',0o600)
    return result

if __name__=='__main__':
    exports();print('Synthetic sessions exported inside the isolated candidate volume; no token printed.')
