"""Oasis-derived Google PKCE flow, with durable browser-bound single-use state."""
import base64
import hashlib
import secrets
import re
from urllib.parse import urlencode
import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from google.auth.exceptions import GoogleAuthError
from flask import Blueprint,current_app,g,request,redirect
from .core import ApiError,DAY,now,iso,uid,token,sha,digest,encrypt,decrypt,body,ok,row,version,audit,replay,remember,paginate,fail
from .db import connect,transaction
from .security import new_session,require_staff,limit,trusted_ip
from .validation import email,enum,text

bp=Blueprint('auth',__name__)
RETURN_PATHS={'/admin/requests','/admin/settings','/admin/locations','/admin/notices','/admin/team','/admin/emails','/admin/audit'}
GMAIL_SCOPE='https://www.googleapis.com/auth/gmail.send'

def invite(c,raw):
    r=c.execute('SELECT * FROM invitations WHERE token_hash=?',(digest('invite',raw),)).fetchone()
    if not r or r['expires_at']<=now() or r['accepted_at'] or r['revoked_at']:raise ApiError('INVITE_UNAVAILABLE',410)
    return r

def start(p,purpose='login'):
    if not current_app.config['GOOGLE_CLIENT_ID'] or not current_app.config['GOOGLE_CLIENT_SECRET']:raise ApiError('INTEGRATION_UNAVAILABLE',503,retryable=True)
    path=p.get('returnTo','/admin/requests' if purpose=='login' else '/admin/emails')
    if not isinstance(path,str) or len(path)>256 or not (path in RETURN_PATHS or path=='/admin/requests/new' or re.fullmatch(r'/admin/(?:requests|emails/outbox)/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',path)):fail('returnTo','Choose a staff workspace page.')
    state,nonce,verifier=token(),token(),secrets.token_urlsafe(64)
    with transaction() as c:
        limit(c,'oauth',trusted_ip(),20,3600000)
        invitation=None;connection_version=None
        if purpose=='gmail':
            require_staff(True,c)
            connection=c.execute("SELECT * FROM integration_secrets WHERE name='gmail'").fetchone()
            version(p,connection);connection_version=connection['version']
        elif p.get('inviteToken'):
            raw=text(p['inviteToken'],'inviteToken',1,256)
            limit(c,'invite',raw,5,900000);invitation=invite(c,raw)['token_hash']
        c.execute('INSERT INTO oauth_states VALUES(?,?,?,?,?,?,?,?,?,?,NULL)',(sha(state),sha(g.sid),purpose,encrypt(dict(nonce=nonce,verifier=verifier)),g.member['id'] if purpose=='gmail' else None,g.member['version'] if purpose=='gmail' else None,invitation,connection_version,path,now()+600000))
    query=dict(client_id=current_app.config['GOOGLE_CLIENT_ID'],redirect_uri=current_app.config['PUBLIC_ORIGIN']+'/oauth/callback',response_type='code',scope='openid email'+(' '+GMAIL_SCOPE if purpose=='gmail' else ''),state=state,nonce=nonce,code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),code_challenge_method='S256',prompt='select_account')
    if purpose=='gmail':query.update(access_type='offline',prompt='select_account consent')
    return ok({'authorizationUrl':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(query),'expiresAt':iso(now()+600000)})

@bp.post('/api/v1/auth/google/start')
def google_start():return start(body({'returnTo','inviteToken'}))

@bp.post('/api/v1/auth/invitations/inspect')
def inspect_invite():
    p=body({'token'});raw=text(p.get('token'),'token',1,256)
    with transaction() as c:
        limit(c,'invite-inspect',trusted_ip(),20,3600000);r=invite(c,raw)
        return ok(dict(state='pending',role=r['role'],expiresAt=iso(r['expires_at']),message='Sign in with the Google account this invitation was sent to.'))

def exchange(code,verifier,nonce):
    response=requests.post('https://oauth2.googleapis.com/token',data=dict(code=code,client_id=current_app.config['GOOGLE_CLIENT_ID'],client_secret=current_app.config['GOOGLE_CLIENT_SECRET'],redirect_uri=current_app.config['PUBLIC_ORIGIN']+'/oauth/callback',grant_type='authorization_code',code_verifier=verifier),timeout=(5,15))
    response.raise_for_status();tokens=response.json()
    class BoundedRequest(GoogleRequest):
        def __call__(self,*args,**kwargs):
            kwargs['timeout']=15
            return super().__call__(*args,**kwargs)
    identity=id_token.verify_oauth2_token(tokens['id_token'],BoundedRequest(),current_app.config['GOOGLE_CLIENT_ID'])
    if identity.get('iss') not in ('accounts.google.com','https://accounts.google.com') or identity.get('email_verified') is not True or not secrets.compare_digest(identity.get('nonce',''),nonce) or not identity.get('sub'):raise ValueError('Identity invalid')
    return tokens,identity

def accept_identity(c,state,identity):
    address=email(identity.get('email'))
    sub=identity['sub']
    member=c.execute('SELECT * FROM members WHERE email_norm=?',(address,)).fetchone()
    invitation=None
    if state['invite_hash']:
        invitation=c.execute('SELECT * FROM invitations WHERE token_hash=?',(state['invite_hash'],)).fetchone()
        if not invitation or invitation['accepted_at'] or invitation['revoked_at'] or invitation['expires_at']<=now():raise ApiError('INVITE_UNAVAILABLE',410)
        if not secrets.compare_digest(invitation['email_norm'],address):raise ApiError('INVITE_ACCOUNT_MISMATCH',403)
    bound=c.execute('SELECT id FROM members WHERE google_sub=?',(sub,)).fetchone()
    if (member and member['google_sub'] and member['google_sub']!=sub) or (bound and (not member or bound['id']!=member['id'])):raise ApiError('ACCOUNT_NOT_INVITED',403)
    if invitation:
        if member:
            c.execute('UPDATE members SET active=1,role=?,version=version+1,google_sub=?,bound_at=?,updated_at=? WHERE id=?',(invitation['role'],sub,now(),now(),member['id']))
        else:
            ident=uid();c.execute('INSERT INTO members VALUES(?,?,?,?,1,1,?,?,?)',(ident,address,sub,invitation['role'],now(),now(),now()))
        member=c.execute('SELECT * FROM members WHERE email_norm=?',(address,)).fetchone()
        c.execute('UPDATE invitations SET accepted_at=?,accepted_by=?,encrypted_token=NULL,version=version+1 WHERE id=?',(now(),member['id'],invitation['id']))
        c.execute("UPDATE outbox SET status='cancelled',updated_at=?,version=version+1 WHERE invite_id=? AND status IN ('pending','retry_wait')",(now(),invitation['id']))
    if not member or not member['active']:raise ApiError('ACCOUNT_NOT_INVITED',403)
    if not member['google_sub']:
        c.execute('UPDATE members SET google_sub=?,bound_at=?,updated_at=? WHERE id=?',(sub,now(),now(),member['id']))
    # All prior anonymous/session state is invalidated before issuing a new sid.
    c.execute('UPDATE sessions SET revoked_at=? WHERE sid_hash=?',(now(),state['sid_hash']))
    new_session(c,member)
    audit(c,'auth.signed_in','member',member['id'])

@bp.get('/oauth/callback')
def callback():
    def denied(code):return redirect('/admin/login?'+urlencode({'error':code}),303)
    raw=request.args.get('state','')
    if not raw or not getattr(g,'sid',None):return denied('signin_expired')
    with transaction() as c:
        state=c.execute('SELECT * FROM oauth_states WHERE state_hash=?',(sha(raw),)).fetchone()
        if not state or state['consumed_at'] or state['expires_at']<=now() or not secrets.compare_digest(state['sid_hash'],sha(g.sid)):return denied('signin_expired')
        state=dict(state)
        c.execute('UPDATE oauth_states SET consumed_at=? WHERE state_hash=?',(now(),sha(raw)))
    if request.args.get('error'):return denied('signin_cancelled')
    try:
        payload=decrypt(state['payload_cipher']);tokens,identity=exchange(request.args.get('code',''),payload['verifier'],payload['nonce'])
        if state['purpose']=='gmail':
            from .mail import replace_sender
            replace_sender(state,tokens,identity)
            return redirect('/admin/emails?connection=connected',303)
        with transaction() as c:accept_identity(c,state,identity)
        return redirect(state['return_to'],303)
    except ApiError as error:
        return denied({'ACCOUNT_NOT_INVITED':'account_not_invited','INVITE_UNAVAILABLE':'invite_unavailable','INVITE_ACCOUNT_MISMATCH':'invite_account_mismatch','SENDER_PERMISSION_DENIED':'sender_permission_denied'}.get(error.code,'signin_expired'))
    except (ValueError,KeyError,requests.RequestException,GoogleAuthError):return denied('google_unavailable')

@bp.get('/api/v1/admin/session')
def session():
    m=g.member;r=g.session;admin=m['role']=='admin'
    return ok(dict(member=dict(id=m['id'],email=m['email_norm'],role=m['role'],version=m['version']),csrfToken=g.csrf,expiresAt=iso(r['absolute_expires_at']),idleExpiresAt=iso(min(r['absolute_expires_at'],now()+7200000)),demoMode=current_app.config['DEMO_MODE'],permissions=dict(requestsWrite=True,settingsWrite=admin,teamWrite=admin,emailManage=admin)))

@bp.post('/api/v1/admin/logout')
def logout():
    body(set())
    with transaction() as c:c.execute('UPDATE sessions SET revoked_at=? WHERE sid_hash=?',(now(),sha(g.sid)))
    g.clear_cookie=True
    return ok(status=204)

def member_view(r):
    return dict(id=r['id'],email=r['email_norm'],role=r['role'],active=bool(r['active']),googleBound=bool(r['google_sub']),version=r['version'],joinedAt=iso(r['joined_at']))

def invitation_view(r):
    state='accepted' if r['accepted_at'] else 'revoked' if r['revoked_at'] else 'expired' if r['expires_at']<=now() else 'pending'
    return dict(id=r['id'],email=r['email_norm'],role=r['role'],state=state,expiresAt=iso(r['expires_at']),version=r['version'],createdAt=iso(r['created_at']))

@bp.get('/api/v1/admin/team/members')
def members():
    with connect() as c:return ok(paginate(c,'members',member_view,order=('joined_at','id')))

@bp.get('/api/v1/admin/team/invitations')
def invitations():
    with connect() as c:
        state=request.args.get('state') or None
        where='1';args=[]
        if state:
            enum(state,{'pending','accepted','expired','revoked'},'state')
            where="(CASE WHEN accepted_at IS NOT NULL THEN 'accepted' WHEN revoked_at IS NOT NULL THEN 'revoked' WHEN expires_at<=? THEN 'expired' ELSE 'pending' END)=?"
            args=[now(),state]
        return ok(paginate(c,'invitations',invitation_view,where,args,filters={'state':state}))

@bp.post('/api/v1/admin/team/invitations')
def create_invite():
    p=body({'email','role'});p={'email':email(p.get('email')),'role':enum(p.get('role'),{'admin','viewer'},'role')}
    with transaction() as c:
        require_staff(True,c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        if c.execute('SELECT 1 FROM members WHERE email_norm=? AND active=1',(p['email'],)).fetchone():raise ApiError('MEMBER_EXISTS',409)
        c.execute('UPDATE invitations SET revoked_at=?,encrypted_token=NULL,version=version+1 WHERE email_norm=? AND accepted_at IS NULL AND revoked_at IS NULL',(now(),p['email']))
        c.execute("UPDATE outbox SET status='cancelled',updated_at=?,version=version+1 WHERE invite_id IN (SELECT id FROM invitations WHERE email_norm=?) AND status IN ('pending','retry_wait')",(now(),p['email']))
        ident,raw=uid(),token();stamp=now()
        c.execute('INSERT INTO invitations VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL,1)',(ident,digest('invite',raw),encrypt(raw),p['email'],p['role'],g.member['id'],stamp,stamp+DAY))
        url=current_app.config['PUBLIC_ORIGIN']+'/admin/invite#token='+raw
        from .mail import enqueue
        out=enqueue(c,uid(),'team_invite',p['email'],"Invitation to Clarke's staff workspace",'Sign in with your invited Google account. This invitation expires in 24 hours.\n'+url,invite_id=ident)
        result=dict(invitation=invitation_view(row(c,'invitations',ident)),inviteUrl=url,deliveryState=out['status'])
        audit(c,'team.invited','invitation',ident)
        return remember(c,scope,p,result,201,ident)

@bp.delete('/api/v1/admin/team/invitations/<ident>')
def revoke_invite(ident):
    p=body({'expectedVersion'})
    with transaction() as c:
        require_staff(True,c);r=row(c,'invitations',ident);version(p,r)
        if r['accepted_at']:raise ApiError('INVALID_TRANSITION',409)
        if not r['revoked_at']:
            c.execute('UPDATE invitations SET revoked_at=?,encrypted_token=NULL,version=version+1 WHERE id=?',(now(),ident))
            c.execute("UPDATE outbox SET status='cancelled',version=version+1,updated_at=? WHERE invite_id=? AND status IN ('pending','retry_wait')",(now(),ident))
            audit(c,'team.invite_revoked','invitation',ident)
    return ok(status=204)

@bp.route('/api/v1/admin/team/members/<ident>',methods=['PATCH','DELETE'])
def edit_member(ident):
    p=body({'expectedVersion','role'} if request.method=='PATCH' else {'expectedVersion'})
    if request.method=='PATCH':p['role']=enum(p.get('role'),{'admin','viewer'},'role')
    with transaction() as c:
        require_staff(True,c);scope=g.member['id']
        if request.method=='PATCH':
            prior=replay(c,scope,p)
            if prior:return prior
        r=row(c,'members',ident);version(p,r)
        removing=request.method=='DELETE';role=r['role'] if removing else p['role']
        if r['active'] and r['google_sub'] and r['role']=='admin' and (removing or role!='admin'):
            if c.execute("SELECT COUNT(*) FROM members WHERE active=1 AND google_sub IS NOT NULL AND role='admin' AND id<>?",(ident,)).fetchone()[0]==0:raise ApiError('LAST_ADMIN',409)
        c.execute('UPDATE members SET role=?,active=?,version=version+1,updated_at=? WHERE id=?',(role,0 if removing else r['active'],now(),ident))
        c.execute('UPDATE sessions SET revoked_at=? WHERE member_id=?',(now(),ident))
        if removing:c.execute('UPDATE invitations SET revoked_at=?,encrypted_token=NULL WHERE email_norm=? AND accepted_at IS NULL',(now(),r['email_norm']))
        audit(c,'team.member_removed' if removing else 'team.role_changed','member',ident,r['version'],r['version']+1)
        if ident==g.member['id']:g.clear_cookie=True
        return ok(status=204) if removing else remember(c,scope,p,dict(id=ident,role=role,active=bool(r['active']),version=r['version']+1))
