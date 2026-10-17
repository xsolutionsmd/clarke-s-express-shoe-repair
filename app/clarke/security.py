import base64
import hashlib
import hmac
import ipaddress
import secrets
from flask import current_app, g, request
from itsdangerous import BadSignature, SignatureExpired
from .core import ApiError, DAY, now, token, sha, digest
from .db import connect, transaction

def csrf_for(sid):
    key=hmac.new(current_app.secret_key,b'clarke-csrf-v1',hashlib.sha256).digest()
    return base64.urlsafe_b64encode(hmac.new(key,sid.encode(),hashlib.sha256).digest()).decode().rstrip('=')

def new_session(c, member=None):
    sid=token();stamp=now();csrf=csrf_for(sid)
    absolute=stamp+(12*3600000 if member else DAY)
    idle=min(absolute,stamp+2*3600000) if member else absolute
    c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,NULL,?)',(sha(sid),sha(csrf),member['id'] if member else None,member['version'] if member else None,stamp,stamp,absolute,idle,'google' if member else 'anonymous'))
    g.new_cookie=current_app.extensions['sessions'].dumps({'sid':sid})
    g.sid=sid;g.csrf=csrf
    g.session=dict(c.execute('SELECT * FROM sessions WHERE sid_hash=?',(sha(sid),)).fetchone())
    g.member=dict(member) if member else None
    return g.session

def load_session(c):
    g.session=None;g.member=None;g.sid=None;g.expired=False
    raw=request.cookies.get('clarke_session')
    if not raw:return
    try:
        sid=current_app.extensions['sessions'].loads(raw,max_age=86400)['sid']
        if not isinstance(sid,str) or len(sid)!=43:return
    except (BadSignature,SignatureExpired,KeyError,TypeError):
        g.expired=True;return
    r=c.execute('SELECT * FROM sessions WHERE sid_hash=?',(sha(sid),)).fetchone()
    if not r or r['revoked_at'] or min(r['absolute_expires_at'],r['idle_expires_at'])<=now():
        g.expired=True;return
    if r['member_id']:
        member=c.execute('SELECT * FROM members WHERE id=? AND active=1 AND google_sub IS NOT NULL',(r['member_id'],)).fetchone()
        if not member or r['auth_method']!='google' or r['member_version']!=member['version']:
            g.expired=True;return
        g.member=dict(member)
    g.sid=sid;g.csrf=csrf_for(sid);g.session=dict(r)

def require_staff(admin=False,c=None):
    if c is not None:load_session(c)
    if not getattr(g,'member',None):raise ApiError('SESSION_EXPIRED' if getattr(g,'expired',False) else 'AUTH_REQUIRED',401)
    if admin and g.member['role']!='admin':raise ApiError('FORBIDDEN',403)

def trusted_ip():
    remote=request.remote_addr or 'unknown'
    # Forwarding is used only for an explicitly configured immediate gateway.
    trusted=current_app.config.get('TRUSTED_PROXY_IP','')
    if trusted and remote==trusted:
        candidate=request.headers.get('X-Forwarded-For','').split(',')[0].strip()
        try:return str(ipaddress.ip_address(candidate))
        except ValueError:pass
    return remote

def limit(c,name,identity,capacity,period,cost=1):
    stamp=now();key=digest('limit',name+'\0'+identity)
    r=c.execute('SELECT * FROM rate_limits WHERE bucket_key=?',(key,)).fetchone()
    balance=min(capacity,r['tokens']+(stamp-r['refill_at'])*capacity/period) if r else capacity
    if balance<cost:
        seconds=max(1,int((cost-balance)*period/capacity/1000)+1)
        raise ApiError('RATE_LIMITED',429,details={'retryAfterSeconds':seconds},retryable=True)
    c.execute('INSERT INTO rate_limits VALUES(?,?,?,?) ON CONFLICT(bucket_key) DO UPDATE SET tokens=excluded.tokens,refill_at=excluded.refill_at,expires_at=excluded.expires_at',(key,balance-cost,stamp,stamp+period+DAY))

def guard():
    g.request_id=token()[:22]
    if not request.path.startswith(('/api/','/oauth/','/admin')):return
    with connect() as c:load_session(c)
    admin_path=request.path.startswith('/api/v1/admin/')
    if admin_path:
        management=not request.path.startswith(('/api/v1/admin/requests','/api/v1/admin/session','/api/v1/admin/logout'))
        require_staff(management)
        with transaction() as c:
            require_staff(management,c)
            limit(c,'staff-write' if request.method not in ('GET','HEAD') else 'staff-read',g.member['id'],60 if request.method not in ('GET','HEAD') else 300,60000)
            c.execute('UPDATE sessions SET last_seen_at=?,idle_expires_at=MIN(absolute_expires_at,?) WHERE sid_hash=?',(now(),now()+7200000,sha(g.sid)))
    if request.path.startswith('/api/') and request.method in ('POST','PUT','PATCH','DELETE'):
        if request.headers.get('Origin')!=current_app.config['PUBLIC_ORIGIN']:raise ApiError('ORIGIN_DENIED',403)
        supplied=request.headers.get('X-CSRF-Token','')
        if not getattr(g,'session',None) or not supplied or not secrets.compare_digest(sha(supplied),g.session['csrf_hash']):raise ApiError('CSRF_INVALID',403)

def cookie(response):
    if getattr(g,'clear_cookie',False):response.delete_cookie('clarke_session',path='/')
    elif getattr(g,'new_cookie',None):response.set_cookie('clarke_session',g.new_cookie,max_age=86400,secure=current_app.config['PUBLIC_ORIGIN'].startswith('https:'),httponly=True,samesite='Lax',path='/')
    return response
