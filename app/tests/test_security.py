import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse,parse_qs
import pytest
from conftest import staff,headers,submit,identify
from clarke import core,db,auth,mail

def test_every_admin_mutation_checks_origin_and_csrf(app):
    c,h,_=staff(app)
    for method,path in routes(app):
        if method=='GET':continue
        for changed,code in [({'Origin':'https://foreign.example.test'},'ORIGIN_DENIED'),({'X-CSRF-Token':'invalid'},'CSRF_INVALID')]:
            with app.app_context(),db.transaction() as connection:connection.execute('DELETE FROM rate_limits')
            r=c.open(path,method=method,json={},headers=h|changed)
            assert r.status_code==403 and r.json['error']['code']==code,(method,path,r.json)

def test_privileged_html_paths_are_guarded(app):
    paths=['/admin/requests','/admin/requests/new','/admin/requests/'+str(uuid.uuid4()),'/admin/settings','/admin/locations','/admin/notices','/admin/team','/admin/emails','/admin/emails/outbox/'+str(uuid.uuid4()),'/admin/audit']
    for client in (app.test_client(),staff(app,expired=True)[0]):
        for path in paths:
            r=client.get(path)
            assert r.status_code==303 and r.location=='/admin/login'
    viewer,_,_=staff(app,'viewer')
    for path in paths[3:]:assert viewer.get(path).status_code==403

def test_forwarding_headers_cannot_bypass_lookup_limit(app,client):
    h=headers(client)
    for n in range(5):
        r=client.post('/api/v1/status/lookup',json={'reference':'wrong','verification':{}},headers=h|{'X-Forwarded-For':'192.0.2.'+str(n)})
        assert r.status_code==404
    r=client.post('/api/v1/status/lookup',json={'reference':'wrong','verification':{}},headers=h|{'X-Forwarded-For':'192.0.2.99'})
    assert r.status_code==429
def routes(app):
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith('/api/v1/admin/'):
            path=rule.rule.replace('<ident>',str(uuid.uuid4())).replace('<photo_id>',str(uuid.uuid4()))
            for collection in ('events','notes','offers','contact-actions') if '<collection>' in path else ('',):
                for method in rule.methods-{'HEAD','OPTIONS'}:yield method,path.replace('<collection>',collection)

@pytest.mark.parametrize('identity',['anonymous','expired','revoked','inactive','wrong_version','unbound'])
def test_every_admin_api_requires_current_google_session(app,identity):
    if identity=='anonymous':c=app.test_client();h=headers(c)
    else:
        c,h,ident=staff(app,expired=identity=='expired')
        with app.app_context(),db.transaction() as connection:
            if identity=='revoked':connection.execute('UPDATE sessions SET revoked_at=? WHERE member_id=?',(core.now(),ident))
            if identity=='inactive':connection.execute('UPDATE members SET active=0 WHERE id=?',(ident,))
            if identity=='wrong_version':connection.execute('UPDATE members SET version=2 WHERE id=?',(ident,))
            if identity=='unbound':connection.execute('UPDATE members SET google_sub=NULL WHERE id=?',(ident,))
    for method,path in routes(app):
        response=c.open(path,method=method,json={} if method!='GET' else None,headers=h)
        assert response.status_code==401,(identity,method,path,response.json)

def test_viewer_denied_all_management_routes(app):
    c,h,_=staff(app,'viewer')
    for method,path in routes(app):
        if path.startswith(('/api/v1/admin/requests','/api/v1/admin/session','/api/v1/admin/logout')):continue
        response=c.open(path,method=method,json={} if method!='GET' else None,headers=h)
        assert response.status_code==403,(method,path,response.json)

def test_last_admin_atomic_race(app):
    first,h1,id1=staff(app);second,h2,id2=staff(app)
    # Each request removes itself. Serialized writes must leave exactly one bound admin.
    def remove(args):
        c,h,ident=args
        return c.delete('/api/v1/admin/team/members/'+ident,json={'expectedVersion':1},headers=h)
    with ThreadPoolExecutor(2) as pool:responses=list(pool.map(remove,[(first,h1,id1),(second,h2,id2)]))
    assert sorted(x.status_code for x in responses)==[204,409]
    assert next(x for x in responses if x.status_code==409).json['error']['code']=='LAST_ADMIN'
    with app.app_context(),db.connect() as c:assert c.execute("SELECT count(*) FROM members WHERE active=1 AND google_sub IS NOT NULL AND role='admin'").fetchone()[0]==1

def begin(c,h,invite=None):
    r=c.post('/api/v1/auth/google/start',json={'returnTo':'/admin/requests','inviteToken':invite},headers=h)
    assert r.status_code==200,r.json
    return {k:v[0] for k,v in parse_qs(urlparse(r.json['data']['authorizationUrl']).query).items()}

def identity(address,sub=None):return dict(email=address,email_verified=True,sub=sub or 'sub-'+address,iss='https://accounts.google.com')

def test_google_state_binding_once_and_initial_account(app,monkeypatch):
    c=app.test_client();h=headers(c);flow=begin(c,h)
    assert flow['code_challenge_method']=='S256' and flow['redirect_uri'].endswith('/oauth/callback')
    other=app.test_client();headers(other)
    assert 'signin_expired' in other.get('/oauth/callback?state='+flow['state']+'&code=ignored').location
    monkeypatch.setattr(auth,'exchange',lambda *args:({},identity('first@example.test')))
    r=c.get('/oauth/callback?state='+flow['state']+'&code=ignored');assert r.status_code==303 and r.location=='/admin/requests'
    assert c.get('/api/v1/admin/session').json['data']['member']['email']=='first@example.test'
    assert 'signin_expired' in c.get('/oauth/callback?state='+flow['state']+'&code=ignored').location
    old=c.get_cookie('clarke_session').value
    c.post('/api/v1/admin/logout',json={},headers=headers(c))
    c.set_cookie('clarke_session',old);assert c.get('/api/v1/admin/session').status_code==401

def test_invite_bound_wrong_used_expired_and_sub_mismatch(app,monkeypatch):
    admin,h,_=staff(app)
    created=admin.post('/api/v1/admin/team/invitations',json={'email':'invited@example.test','role':'viewer'},headers=h)
    assert created.status_code==201,created.json
    invitation=created.json['data'];raw=invitation['inviteUrl'].split('#token=')[1]
    c=app.test_client();ch=headers(c)
    inspected=c.post('/api/v1/auth/invitations/inspect',json={'token':raw},headers=ch)
    assert inspected.status_code==200 and 'email' not in inspected.json['data']
    monkeypatch.setattr(auth,'exchange',lambda *args:({},identity('wrong@example.test')))
    flow=begin(c,ch,raw);assert 'invite_account_mismatch' in c.get('/oauth/callback?state='+flow['state']+'&code=ignored').location
    monkeypatch.setattr(auth,'exchange',lambda *args:({},identity('invited@example.test')))
    flow=begin(c,ch,raw);assert c.get('/oauth/callback?state='+flow['state']+'&code=ignored').location=='/admin/requests'
    assert c.get('/api/v1/admin/session').json['data']['member']['role']=='viewer'
    assert c.post('/api/v1/auth/invitations/inspect',json={'token':raw},headers=headers(c)).status_code==410
    outsider=app.test_client();oh=headers(outsider)
    monkeypatch.setattr(auth,'exchange',lambda *args:({},identity('invited@example.test','different-sub')))
    flow=begin(outsider,oh);assert 'account_not_invited' in outsider.get('/oauth/callback?state='+flow['state']+'&code=ignored').location
    h['Idempotency-Key']=str(uuid.uuid4());new=admin.post('/api/v1/admin/team/invitations',json={'email':'expired@example.test','role':'admin'},headers=h).json['data']
    with app.app_context(),db.transaction() as conn:conn.execute('UPDATE invitations SET expires_at=? WHERE id=?',(core.now()-1,new['invitation']['id']))
    assert outsider.post('/api/v1/auth/invitations/inspect',json={'token':new['inviteUrl'].split('#token=')[1]},headers=oh).status_code==410

def test_oauth_verifier_nonce_and_provider_failure(app,monkeypatch):
    c=app.test_client();h=headers(c)
    assert c.post('/api/v1/auth/google/start',json={'returnTo':'//evil.test'},headers=h).status_code==422
    flow=begin(c,h)
    monkeypatch.setattr(auth,'exchange',lambda *args:(_ for _ in ()).throw(ValueError('private provider detail')))
    result=c.get('/oauth/callback?state='+flow['state']+'&code=secret-code')
    assert result.location=='/admin/login?error=google_unavailable' and 'private' not in result.text
    with app.app_context(),db.connect() as conn:
        payload=conn.execute('SELECT payload_cipher FROM oauth_states').fetchone()[0]
        assert flow['nonce'] not in payload

def test_session_rotation_role_change_and_csrf(app):
    first,h1,id1=staff(app);second,h2,_=staff(app)
    assert second.patch('/api/v1/admin/team/members/'+id1,json={'expectedVersion':1,'role':'viewer'},headers=h2).status_code==200
    assert first.get('/api/v1/admin/session').status_code==401
    assert second.patch('/api/v1/admin/settings',json={'expectedVersion':1,'intakeAccepting':True},headers=h2|{'X-CSRF-Token':'forged'}).status_code==403

def test_public_bearer_does_not_authorize_photos(app,client):
    receipt,_,_=submit(client);ident=identify(app,receipt)
    raw=receipt['statusUrl'].split('#token=')[1]
    assert client.get(f'/api/v1/admin/requests/{ident}/photos/{uuid.uuid4()}',headers={'Authorization':'Bearer '+raw}).status_code==401

def test_demo_customer_links_suppressed_and_exact_allowlist(app):
    c,h,_=staff(app)
    from conftest import repair_body
    from clarke.repairs import REPAIR_FIELDS
    p={k:v for k,v in repair_body('x').items() if k in REPAIR_FIELDS};p['contact']=dict(name='Synthetic',email='allowed+alias@example.test',phone='+12025550124',preferred='text')
    r=c.post('/api/v1/admin/requests',json=p,headers=h);assert r.status_code==201,r.json
    ident=r.json['data']['id']
    assert c.get(f'/api/v1/admin/requests/{ident}/contact-actions').json['data']==dict(callHref=None,smsHref=None,emailHref=None,blockedByDemo=True)
    assert c.post(f'/api/v1/admin/requests/{ident}/share-link',json={'channel':'text'},headers=h).json['data']['deliveryState']=='preview_only'
