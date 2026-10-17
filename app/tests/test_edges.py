import io
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pytest


def test_not_repairable_is_a_branch_and_leaving_it_requires_reason(app,client):
    receipt,_,_=submit(client);ident=identify(app,receipt);c,h,_=staff(app)
    path='/api/v1/admin/requests/'+ident
    assert c.patch(path,json={'expectedVersion':1,'status':'in_progress'},headers=h).status_code==200
    h['Idempotency-Key']=str(uuid.uuid4())
    assert c.patch(path,json={'expectedVersion':2,'status':'not_repairable','customerMessage':'This synthetic material cannot support the repair.'},headers=h).status_code==200
    h['Idempotency-Key']=str(uuid.uuid4())
    assert c.patch(path,json={'expectedVersion':3,'status':'reviewing'},headers=h).status_code==422
    assert c.patch(path,json={'expectedVersion':3,'status':'reviewing','reason':'Customer requested another assessment.'},headers=h).status_code==200

def test_superseded_unsent_offer_cancelled_and_old_failure_not_retryable(app,client):
    from test_mail import connected
    connected(app)
    receipt,_,_=submit(client,contact=dict(name='Synthetic',email='allowed@example.test',phone=None,preferred='email'))
    ident=identify(app,receipt);c,h,_=staff(app)
    path='/api/v1/admin/requests/'+ident
    p=dict(expectedVersion=1,kind='estimate',amountMinCents=1234,amountMaxCents=None,scope='Synthetic sole repair estimate.',timingNote=None,customerMessage=None)
    assert c.post(path+'/offers',json=p,headers=h).status_code==201
    with app.app_context(),db.connect() as connection:
        old=connection.execute("SELECT id FROM outbox WHERE kind='customer_estimate'").fetchone()[0]
    h['Idempotency-Key']=str(uuid.uuid4())
    assert c.patch(path,json={'expectedVersion':2,'status':'ready','pickupLocation':'bel_air'},headers=h).status_code==200
    assert c.get('/api/v1/admin/outbox/'+old).json['data']['status']=='cancelled'
    with app.app_context(),db.transaction() as connection:connection.execute("UPDATE outbox SET status='failed' WHERE id=?",(old,))
    result=c.get('/api/v1/admin/outbox/'+old).json['data']
    assert result['canRetry'] is False
    h['Idempotency-Key']=str(uuid.uuid4())
    assert c.post('/api/v1/admin/outbox/'+old+'/retry',json={'expectedVersion':result['version']},headers=h).status_code==409
from conftest import headers,staff,draft,submit,repair_body,identify,image_bytes,upload
from clarke import core,db,repairs,uploads,mail,locations,validation,maintenance

def test_outbox_insert_failure_rolls_back_ticket_and_recovers(app,client):
    d,h=draft(client);p=repair_body(d['draftId']);h['X-Draft-Token']=d['draftToken']
    with app.app_context(),db.transaction() as c:
        c.execute("CREATE TRIGGER fail_outbox BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    with pytest.raises(sqlite3.IntegrityError):client.post('/api/v1/requests',json=p,headers=h)
    with app.app_context(),db.transaction() as c:
        assert c.execute('SELECT count(*) FROM requests').fetchone()[0]==0
        assert c.execute('SELECT state FROM drafts').fetchone()[0]=='active'
        c.execute('DROP TRIGGER fail_outbox')
    assert client.post('/api/v1/requests',json=p,headers=h).status_code==201

def test_two_responses_and_two_offers_cannot_overwrite(app,client):
    receipt,_,_=submit(client);ident=identify(app,receipt);admin,h,_=staff(app)
    p=dict(expectedVersion=1,kind='estimate',amountMinCents=1234,amountMaxCents=None,scope='Synthetic repair scope for racing offers.',timingNote=None,customerMessage=None)
    cookie=admin.get_cookie('clarke_session').value
    def offer(_):
        c=app.test_client();c.set_cookie('clarke_session',cookie)
        return c.post(f'/api/v1/admin/requests/{ident}/offers',json=p,headers=h|{'Idempotency-Key':str(uuid.uuid4())})
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(offer,range(2)))
    assert sorted(r.status_code for r in results)==[201,409]
    offered=next(r for r in results if r.status_code==201).json['data']
    raw=receipt['statusUrl'].split('#token=')[1];ch=headers(client,Authorization='Bearer '+raw);cookie=client.get_cookie('clarke_session').value
    def response(choice):
        c=app.test_client();c.set_cookie('clarke_session',cookie)
        return c.post('/api/v1/status/responses',json={'offerId':offered['offerId'],'expectedVersion':2,'choice':choice,'phone':None},headers=ch|{'Idempotency-Key':str(uuid.uuid4())})
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(response,['accept','decline']))
    assert sorted(r.status_code for r in results)==[200,409]
    with app.app_context(),db.connect() as c:assert c.execute('SELECT count(*) FROM customer_responses').fetchone()[0]==1

def test_upload_replay_changed_bytes_foreign_draft_and_watermark(app,client):
    d,h=draft(client);h|={'X-Draft-Token':d['draftToken'],'Idempotency-Key':str(uuid.uuid4())};path='/api/v1/drafts/'+d['draftId']+'/photos'
    data=image_bytes()
    first=client.post(path,data={'file':(io.BytesIO(data),'shoe.jpg')},headers=h);assert first.status_code==202
    replay=client.post(path,data={'file':(io.BytesIO(data),'changed-name.jpg')},headers=h);assert replay.status_code==202 and replay.json==first.json
    changed=client.post(path,data={'file':(io.BytesIO(image_bytes(size=(40,30))),'shoe.jpg')},headers=h);assert changed.status_code==409
    another,ah=draft(client)
    assert client.get('/api/v1/drafts/'+d['draftId'],headers={'X-Draft-Token':another['draftToken']}).status_code==404
    app.config['UPLOAD_MIN_FREE_BYTES']=2**63
    assert upload(client,another,ah).status_code==503

def test_canonical_json_unknown_fields_and_secure_cookie(app,client):
    h=headers(client)
    assert client.post('/api/v1/drafts',data='{"x":1,"x":2}',content_type='application/json',headers=h).json['error']['code']=='MALFORMED_JSON'
    assert client.post('/api/v1/drafts',json={'unknown':1},headers=h).status_code==422
    assert client.post('/api/v1/drafts',json={'x':'x'*33000},headers=h).status_code==413
    response=client.get('/api/v1/bootstrap');assert 'no-store' in response.headers['Cache-Control'] and 'no-referrer'==response.headers['Referrer-Policy']
    app.config['PUBLIC_ORIGIN']='https://candidate.example.test';other=app.test_client();cookie=other.get('/api/v1/bootstrap').headers['Set-Cookie']
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie

def test_new_york_needed_by_and_retention_reduction_activation(app,client,monkeypatch):
    instant=int(datetime.fromisoformat('2026-11-02T00:30:00+00:00').timestamp()*1000)
    monkeypatch.setattr(validation,'now',lambda:instant)
    p=repair_body('unused');p['neededBy']='2026-11-01'
    assert validation.repair(p)['neededBy']=='2026-11-01'
    p['neededBy']='2026-10-31'
    with pytest.raises(core.ApiError):validation.repair(p)
    with app.app_context(),db.transaction() as c:
        pending=dict(photoRetentionDays=90,closedLinkDays=60,effectiveAt=core.iso(core.now()-1))
        c.execute('UPDATE settings SET pending_retention=?',(json.dumps(pending),))
    with app.app_context():
        maintenance.reconcile()
        with db.connect() as c:assert db.settings(c)['photoRetentionDays']==90 and c.execute('SELECT pending_retention FROM settings').fetchone()[0] is None

def test_retention_deleted_file_and_metadata_body_purge(app,client):
    d,h=draft(client);photo=upload(client,d,h).json['data']['photoId']
    with app.app_context():assert 'error' not in uploads.process_one()
    p=repair_body(d['draftId']);p['photoIds']=[photo]
    created=client.post('/api/v1/requests',json=p,headers=h|{'X-Draft-Token':d['draftToken'],'Idempotency-Key':str(uuid.uuid4())});assert created.status_code==201
    ident=identify(app,created.json['data'])
    with app.app_context(),db.transaction() as c:
        c.execute("UPDATE requests SET status='picked_up',closed_at=? WHERE id=?",(core.now()-181*core.DAY,ident))
        c.execute('UPDATE outbox SET updated_at=?',(core.now()-91*core.DAY,))
        key=c.execute('SELECT sanitized_key FROM photos').fetchone()[0]
    with app.app_context():
        maintenance.reconcile()
        assert not uploads.storage(key).exists()
        maintenance.reconcile()
        with db.connect() as c:
            assert c.execute('SELECT state FROM photos').fetchone()[0]=='deleted'
            assert c.execute("SELECT count(*) FROM audit_events WHERE action='photo.deleted' AND entity_id=?",(photo,)).fetchone()[0]==1
            assert c.execute('SELECT body_cipher FROM outbox').fetchone()[0] is None
            assert c.execute('SELECT count(*) FROM requests').fetchone()[0]==1

def test_version_requires_and_noop_no_mail(app,client):
    receipt,_,_=submit(client);ident=identify(app,receipt);c,h,_=staff(app)
    assert c.patch('/api/v1/admin/requests/'+ident,json={'status':'reviewing'},headers=h).status_code==428
    r=c.patch('/api/v1/admin/requests/'+ident,json={'expectedVersion':1,'status':'new'},headers=h);assert r.json['data']['version']==1
    with app.app_context(),db.connect() as conn:assert conn.execute('SELECT count(*) FROM outbox').fetchone()[0]==2

def test_invite_and_gmail_permission_failure_preserve_connection(app,monkeypatch):
    from test_mail import connected
    from urllib.parse import parse_qs,urlparse
    from clarke import auth
    connected(app);c,h,_=staff(app)
    r=c.post('/api/v1/admin/email/connect',json={'expectedVersion':1,'returnTo':'/admin/emails'},headers=h)
    state=parse_qs(urlparse(r.json['data']['authorizationUrl']).query)['state'][0]
    monkeypatch.setattr(auth,'exchange',lambda *args:({'scope':'openid email'},{'email':'other@example.test','sub':'other'}))
    assert c.get('/oauth/callback?state='+state+'&code=ignored').location.endswith('sender_permission_denied')
    assert c.get('/api/v1/admin/email/connection').json['data']['senderEmail']=='sender@example.test'
