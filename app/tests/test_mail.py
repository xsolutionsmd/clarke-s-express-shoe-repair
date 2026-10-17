import json
import uuid
import requests
import pytest
from conftest import staff,headers,submit,identify
from clarke import core,db,mail,auth

def connected(app,enabled=True):
    with app.app_context(),db.transaction() as c:
        sender=dict(email='sender@example.test',sub='sender-sub',refresh_token='synthetic-refresh',access_token='synthetic-access',expires_at=core.now()+3600000)
        c.execute("UPDATE integration_secrets SET ciphertext=?,state='connected',connected_at=? WHERE name='gmail'",(core.encrypt(sender),core.now()))
        values=db.settings(c);values['emailDeliveryEnabled']=enabled;db.save_settings(c,values)

def queue_test(app):
    c,h,_=staff(app);r=c.post('/api/v1/admin/email/test',json={'recipient':'allowed@example.test'},headers=h);assert r.status_code==202,r.json
    return c,h,r.json['data']['outboxId']

def result(app,ident):
    with app.app_context(),db.connect() as c:return dict(c.execute('SELECT * FROM outbox WHERE id=?',(ident,)).fetchone())

class Response:
    def __init__(self,status=200,payload=None):self.status_code=status;self.ok=status<400;self.headers={};self.payload=payload or {'id':'synthetic-provider-message'}
    def json(self):return self.payload

def test_demo_allowlist_encrypted_preview_and_no_send(app,client,monkeypatch):
    connected(app)
    receipt,_,_=submit(client)
    monkeypatch.setattr(mail.requests,'post',lambda *a,**k:pytest.fail('Unexpected provider request'))
    with app.app_context():mail.drain_one()
    admin,h,_=staff(app)
    assert admin.post('/api/v1/admin/email/test',json={'recipient':'blocked@example.test'},headers=h).status_code==403
    rows=admin.get('/api/v1/admin/outbox').json['data']['items'];assert {x['status'] for x in rows}=={'preview_only'}
    detail=admin.get('/api/v1/admin/outbox/'+rows[0]['id']).json['data'];assert '<script' not in detail['bodyHtml'] and not detail['bodyPurged']
    assert '<a href="'+app.config['PUBLIC_ORIGIN']+'/' in detail['bodyHtml']

@pytest.mark.parametrize('mode,expected',[('ok','sent'),('connect_timeout','retry_wait'),('read_timeout','uncertain'),('server_error','uncertain'),('rate_limit','retry_wait'),('rejected','failed')])
def test_delivery_outcomes(app,monkeypatch,mode,expected):
    connected(app);admin,h,ident=queue_test(app)
    def transport(*a,**k):
        if mode=='connect_timeout':raise requests.ConnectTimeout()
        if mode=='read_timeout':raise requests.ReadTimeout()
        return Response({'ok':200,'server_error':500,'rate_limit':429,'rejected':400}.get(mode,200))
    monkeypatch.setattr(mail.requests,'post',transport)
    with app.app_context():mail.drain_one()
    assert result(app,ident)['status']==expected
    if expected=='uncertain':
        data=admin.get('/api/v1/admin/outbox/'+ident).json['data'];assert data['retryNeedsDuplicateAcknowledgement']
        p=dict(expectedVersion=data['version'],acknowledgePossibleDuplicate=False)
        assert admin.post('/api/v1/admin/outbox/'+ident+'/retry',json=p,headers=h|{'Idempotency-Key':str(uuid.uuid4())}).status_code==409
        r=admin.post('/api/v1/admin/outbox/'+ident+'/retry',json=p|{'acknowledgePossibleDuplicate':True},headers=h|{'Idempotency-Key':str(uuid.uuid4())});assert r.status_code==202,r.json

def test_disconnected_sender_does_not_lose_intake(app,client):
    connected(app)
    with app.app_context(),db.transaction() as c:c.execute("UPDATE integration_secrets SET state='reconnect_required'")
    receipt,_,_=submit(client,contact=dict(name='Synthetic Allowed',email='allowed@example.test',phone=None,preferred='email'))
    with app.app_context():mail.drain_one()
    ident=identify(app,receipt)
    with app.app_context(),db.connect() as c:
        assert c.execute('SELECT count(*) FROM requests WHERE id=?',(ident,)).fetchone()[0]==1
        assert c.execute("SELECT status FROM outbox WHERE recipient_norm='allowed@example.test'").fetchone()[0]=='failed'

def test_safe_retry_refresh_reauth_expired_lease_and_disconnect(app,monkeypatch):
    connected(app);admin,h,ident=queue_test(app)
    with app.app_context(),db.transaction() as c:
        sender=core.decrypt(mail.connection(c)['ciphertext']);sender['expires_at']=0;c.execute('UPDATE integration_secrets SET ciphertext=?',(core.encrypt(sender),))
    monkeypatch.setattr(mail.requests,'post',lambda *a,**k:Response(400,{'error':'invalid_grant'}))
    with app.app_context():mail.drain_one()
    assert result(app,ident)['status']=='failed'
    assert admin.get('/api/v1/admin/email/connection').json['data']['requiresReconnect']
    connected(app)
    r=result(app,ident)
    assert admin.post('/api/v1/admin/outbox/'+ident+'/retry',json={'expectedVersion':r['version']},headers=h|{'Idempotency-Key':str(uuid.uuid4())}).status_code==202
    monkeypatch.setattr(mail.requests,'post',lambda *a,**k:Response())
    with app.app_context():mail.drain_one()
    assert result(app,ident)['status']=='sent'
    version=admin.get('/api/v1/admin/email/connection').json['data']['version']
    response=admin.post('/api/v1/admin/email/disconnect',json={'expectedVersion':version},headers=h|{'Idempotency-Key':str(uuid.uuid4())});assert response.status_code==200,response.json
    with app.app_context(),db.connect() as c:
        assert mail.connection(c)['ciphertext'] is None
        assert c.execute('SELECT encrypted_token FROM revocations').fetchone()[0]!='synthetic-refresh'
        assert not db.settings(c)['emailDeliveryEnabled']

def test_worker_lease_uncertain_and_stale_message_cancel(app,client):
    connected(app);_,_,ident=queue_test(app)
    with app.app_context(),db.transaction() as c:c.execute("UPDATE outbox SET status='sending',lease_expires_at=? WHERE id=?",(core.now()-1,ident))
    with app.app_context():mail.drain_one()
    assert result(app,ident)['status']=='uncertain'

def test_gmail_connection_separate_from_staff_identity(app,monkeypatch):
    admin,h,member=staff(app)
    result=admin.post('/api/v1/admin/email/connect',json={'expectedVersion':1,'returnTo':'/admin/emails'},headers=h);assert result.status_code==200,result.json
    from urllib.parse import parse_qs,urlparse
    state=parse_qs(urlparse(result.json['data']['authorizationUrl']).query)['state'][0]
    monkeypatch.setattr(auth,'exchange',lambda *args:({'scope':'openid email '+auth.GMAIL_SCOPE,'refresh_token':'synthetic-refresh','access_token':'synthetic-access'},{'email':'sender@example.test','sub':'sender-sub'}))
    response=admin.get('/oauth/callback?state='+state+'&code=ignored');assert response.location=='/admin/emails?connection=connected'
    assert admin.get('/api/v1/admin/session').json['data']['member']['id']==member
    assert admin.get('/api/v1/admin/email/connection').json['data']['senderEmail']=='sender@example.test'
