import io
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
import pytest
from conftest import headers,staff,draft,submit,repair_body,identify,image_bytes,upload,ORIGIN
from clarke import core,db,repairs,locations,uploads,auth,mail,maintenance

def test_credential_free_health_and_initial_admin(tmp_path):
    from server import create_app
    a=create_app({'TESTING':True,'DATA_DIR':str(tmp_path),'PUBLIC_ORIGIN':ORIGIN})
    c=a.test_client();assert c.get('/health').json=={'status':'ok'}
    assert c.get('/api/v1/bootstrap').json['data']['googleReady'] is False
    assert c.get('/api/v1/admin/session').status_code==401
    assert c.post('/api/v1/auth/google/start',json={},headers=headers(c)).status_code==503
    with a.app_context(),db.connect() as conn:assert conn.execute('SELECT count(*) FROM members').fetchone()[0]==0

def test_keys_restart_migrations_and_no_reseed(app):
    from server import create_app
    with app.app_context(),db.transaction() as c:
        c.execute("UPDATE members SET active=0 WHERE email_norm='first@example.test'")
        checks=[tuple(x) for x in c.execute('SELECT version,checksum FROM schema_migrations')]
    again=create_app(app.config)
    assert again.secret_key==app.secret_key
    with again.app_context(),db.connect() as c:
        assert c.execute("SELECT active FROM members WHERE email_norm='first@example.test'").fetchone()[0]==0
        assert checks==[tuple(x) for x in c.execute('SELECT version,checksum FROM schema_migrations')]
    with pytest.raises(RuntimeError):create_app(dict(app.config,SESSION_SECRET='mismatch'))

def test_public_validation_origin_csrf_privacy(client,app):
    assert client.post('/api/v1/drafts',json={}).status_code==403
    h=headers(client)
    assert client.post('/api/v1/drafts',json={},headers=h|{'Origin':'https://evil.test'}).status_code==403
    assert client.post('/api/v1/drafts',json={},headers={k:v for k,v in h.items() if k!='Origin'}).status_code==403
    d,h=draft(client);h['X-Draft-Token']=d['draftToken'];p=repair_body(d['draftId'])
    for key,value in [('description','short'),('itemType','unknown'),('neededBy','2020-01-01'),('workTypes',['not_sure','zipper']),('website','bot')]:
        r=client.post('/api/v1/requests',json=p|{key:value},headers=h);assert r.status_code==422,r.json
    for preferred in ('call','text'):
        assert client.post('/api/v1/requests',json=p|{'contact':p['contact']|{'preferred':preferred}},headers=h).status_code==422
    r=client.post('/api/v1/requests',json=p,headers=h);assert r.status_code==201,r.json
    token=r.json['data']['statusUrl'].split('#token=')[1]
    public=client.get('/api/v1/status',headers={'Authorization':'Bearer '+token}).json['data']
    assert not set(public)&{'contact','photos','description','brandAge','neededBy','notes'}
    assert p['contact']['name'] not in json.dumps(public)
    for path in ('/data/secret.key','/uploads/a.jpg','/api/v1/missing','/oauth/missing','/tests/seed','/api/test-login'):
        assert client.get(path).status_code==404

def test_submission_idempotency_draft_pause_and_outbox(client,app):
    receipt,p,h=submit(client,location='dundalk')
    again=client.post('/api/v1/requests',json=p,headers=h)
    assert again.status_code==200 and again.json['data']==receipt and again.headers['Idempotency-Replayed']=='true'
    assert client.post('/api/v1/requests',json=p|{'description':'A changed description of the repair.'},headers=h).status_code==409
    assert client.post('/api/v1/requests',json=p,headers=h|{'Idempotency-Key':str(uuid.uuid4())}).json['data']==receipt
    assert receipt['appointmentConfirmed'] is False and '443-386-3800' in receipt['locationMessage']
    with app.app_context(),db.connect() as c:
        assert c.execute('SELECT count(*) FROM requests').fetchone()[0]==1
        out=list(c.execute('SELECT * FROM outbox'));assert len(out)==2 and {x['status'] for x in out}=={'preview_only'}
        assert p['contact']['email'] not in out[0]['body_cipher']
    admin,ah,_=staff(app)
    assert admin.patch('/api/v1/admin/settings',json={'expectedVersion':1,'intakeAccepting':False,'intakePauseMessage':'Please call the shop.'},headers=ah).status_code==200
    assert client.post('/api/v1/requests',json=p,headers=h).status_code==200
    d,nh=draft(client);np=repair_body(d['draftId'])
    assert client.post('/api/v1/requests',json=np,headers=nh|{'X-Draft-Token':d['draftToken']}).json['error']['code']=='INTAKE_PAUSED'
    assert client.get('/api/v1/drafts/'+d['draftId'],headers={'X-Draft-Token':d['draftToken']}).status_code==200

def test_duplicate_submit_race(app,client):
    d,h=draft(client);h|={'X-Draft-Token':d['draftToken']};p=repair_body(d['draftId']);cookie=client.get_cookie('clarke_session').value
    def run(_):
        c=app.test_client();c.set_cookie('clarke_session',cookie)
        return c.post('/api/v1/requests',json=p,headers=h)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,range(2)))
    assert sorted(x.status_code for x in results)==[200,201]
    assert results[0].json==results[1].json

def test_offers_responses_conflicts_and_no_private_note(app,client):
    receipt,_,_=submit(client);ident=identify(app,receipt);admin,h,_=staff(app,'viewer')
    offer={'expectedVersion':1,'kind':'estimate','amountMinCents':1234,'amountMaxCents':2345,'scope':'Replace the worn synthetic test soles.','timingNote':None,'customerMessage':'Please review this estimate.'}
    result=admin.post(f'/api/v1/admin/requests/{ident}/offers',json=offer,headers=h);assert result.status_code==201,result.json
    offer_id=result.json['data']['offerId'];token=receipt['statusUrl'].split('#token=')[1]
    h2=headers(client,Authorization='Bearer '+token)
    p={'offerId':offer_id,'expectedVersion':2,'choice':'accept','phone':None}
    accepted=client.post('/api/v1/status/responses',json=p,headers=h2);assert accepted.status_code==200,accepted.json
    assert accepted.json['data']['status']=='awaiting_dropoff'
    assert client.post('/api/v1/status/responses',json=p,headers=h2).json==accepted.json
    assert client.post('/api/v1/status/responses',json=p,headers=h2|{'Idempotency-Key':str(uuid.uuid4())}).json['error']['code']=='RESPONSE_ALREADY_RECORDED'
    n=admin.post(f'/api/v1/admin/requests/{ident}/notes',json={'expectedVersion':3,'text':'Internal synthetic note never public.'},headers=h|{'Idempotency-Key':str(uuid.uuid4())});assert n.status_code==201,n.json
    conflict=admin.patch(f'/api/v1/admin/requests/{ident}',json={'expectedVersion':3,'status':'in_shop'},headers=h|{'Idempotency-Key':str(uuid.uuid4())});assert conflict.json['error']['code']=='VERSION_CONFLICT'
    public=client.get('/api/v1/status',headers={'Authorization':'Bearer '+token})
    assert 'Internal synthetic' not in public.text
    assert 'customer@example' not in public.text

@pytest.mark.parametrize('choice',['decline','request_call'])
def test_visit_response_and_supersession(app,client,choice):
    receipt,_,_=submit(client);ident=identify(app,receipt);admin,h,_=staff(app)
    p=dict(expectedVersion=1,kind='visit',amountMinCents=None,amountMaxCents=None,scope='Bring your item in for assessment.',timingNote=None,customerMessage=None)
    first=admin.post(f'/api/v1/admin/requests/{ident}/offers',json=p,headers=h).json['data']
    second=admin.post(f'/api/v1/admin/requests/{ident}/offers',json=p|{'expectedVersion':2},headers=h|{'Idempotency-Key':str(uuid.uuid4())}).json['data']
    token=receipt['statusUrl'].split('#token=')[1];ch=headers(client,Authorization='Bearer '+token)
    response=dict(offerId=first['offerId'],expectedVersion=3,choice=choice,phone='+12025550123' if choice=='request_call' else None)
    assert client.post('/api/v1/status/responses',json=response,headers=ch).json['error']['code']=='OFFER_SUPERSEDED'
    r=client.post('/api/v1/status/responses',json=response|{'offerId':second['offerId']},headers=ch)
    assert r.status_code==200,r.json
    assert r.json['data']['status']==('cancelled' if choice=='decline' else 'needs_visit')

def test_lookup_uniform_and_expiry_reopen(app,client):
    receipt,p,_=submit(client,contact=dict(name='Synthetic',email='lookup@example.test',phone='+12025550123',preferred='email'))
    h=headers(client)
    for verification in [{'type':'email','value':'LOOKUP@example.test'},{'type':'phone_last4','value':'0123'}]:
        assert client.post('/api/v1/status/lookup',json={'reference':receipt['reference'],'verification':verification},headers=h).status_code==200
    bad1=client.post('/api/v1/status/lookup',json={'reference':receipt['reference'],'verification':{'type':'email','value':'wrong@example.test'}},headers=h)
    bad2=client.post('/api/v1/status/lookup',json={'reference':'bad','verification':{'type':'email','value':'wrong@example.test'}},headers=h)
    assert bad1.status_code==bad2.status_code==404 and bad1.json['error']['message']==bad2.json['error']['message']
    ident=identify(app,receipt);admin,ah,_=staff(app)
    with app.app_context(),db.transaction() as c:c.execute("UPDATE requests SET status='picked_up',closed_at=? WHERE id=?",(core.now()-91*core.DAY,ident))
    old=receipt['statusUrl'].split('#token=')[1]
    assert client.get('/api/v1/status',headers={'Authorization':'Bearer '+old}).status_code==404
    r=admin.patch('/api/v1/admin/requests/'+ident,json={'expectedVersion':1,'status':'reviewing','reason':'Reopened after customer called.'},headers=ah);assert r.status_code==200,r.json
    assert client.get('/api/v1/status',headers={'Authorization':'Bearer '+old}).status_code==404
    fresh=admin.post(f'/api/v1/admin/requests/{ident}/share-link',json={'channel':'print'},headers=ah).json['data']['statusUrl'].split('#token=')[1]
    assert fresh!=old and client.get('/api/v1/status',headers={'Authorization':'Bearer '+fresh}).status_code==200

def test_walkin_contact_actions_ready_and_search(app):
    c,h,_=staff(app,'viewer');p=repair_body('unused');p={k:v for k,v in p.items() if k in repairs.REPAIR_FIELDS};p['contact']=dict(name='Synthetic Walkin',email=None,phone='+12025550123',preferred='text')
    r=c.post('/api/v1/admin/requests',json=p,headers=h);assert r.status_code==201,r.json
    ident=r.json['data']['id'];h['Idempotency-Key']=str(uuid.uuid4())
    assert c.post(f'/api/v1/admin/requests/{ident}/share-link',json={'channel':'text'},headers=h).json['data']['smsHref'].startswith('sms:+12025550123?body=')
    assert c.get(f'/api/v1/admin/requests/{ident}/contact-actions').json['data']['callHref']=='tel:+12025550123'
    result=c.patch('/api/v1/admin/requests/'+ident,json={'expectedVersion':1,'status':'ready','pickupLocation':'dundalk'},headers=h);assert result.status_code==200,result.json
    assert len(c.get('/api/v1/admin/requests?filter=ready&q=Synthetic').json['data']['items'])==1
    assert c.get('/api/v1/admin/requests?filter=closed').json['data']['items']==[]

def test_settings_retention_notices_and_validation(app):
    c,h,_=staff(app)
    p={'expectedVersion':1,'photoRetentionDays':90,'closedLinkDays':60}
    assert c.patch('/api/v1/admin/settings',json=p,headers=h).status_code==422
    result=c.patch('/api/v1/admin/settings',json=p|{'confirmRetentionReduction':True},headers=h);assert result.status_code==200,result.json
    settings=c.get('/api/v1/admin/settings').json['data'];assert settings['photoRetentionDays']==180 and settings['pendingRetention']['photoRetentionDays']==90
    assert c.post('/api/v1/admin/settings/retention-preview',json={'photoRetentionDays':90,'closedLinkDays':60},headers=h).status_code==200
    bad=[None]*7;bad[2]={'open':'17:00','close':'09:00'}
    assert c.put('/api/v1/admin/hours',json={'expectedVersion':1,'days':bad},headers=h).status_code==422
    notice=dict(locations=['bel_air'],message='Synthetic closure',reopenText=None,startsAt='2027-01-05T09:00:00-05:00',endsAt='2027-01-05T10:00:00-05:00')
    assert c.post('/api/v1/admin/notices/preview',json=notice,headers=h).status_code==200
    r=c.post('/api/v1/admin/notices',json=notice,headers=h);assert r.status_code==201,r.json
    assert c.patch('/api/v1/admin/notices/'+r.json['data']['id'],json={'expectedVersion':1,'message':'Updated synthetic closure'},headers=h|{'Idempotency-Key':str(uuid.uuid4())}).status_code==200

def test_rate_limits_and_database_lock(app,client):
    h=headers(client)
    for _ in range(5):client.post('/api/v1/status/lookup',json={'reference':'wrong','verification':{}},headers=h)
    r=client.post('/api/v1/status/lookup',json={'reference':'wrong','verification':{}},headers=h)
    assert r.status_code==429 and int(r.headers['Retry-After'])>0
    with app.app_context(),db.transaction() as c:
        result=client.post('/api/v1/drafts',json={},headers=h)
        assert result.status_code==503 and result.json['error']['code']=='DATABASE_BUSY'

def test_replacement_and_complete_data_restore(app,client,tmp_path):
    import shutil
    from server import create_app
    d,h=draft(client);p=upload(client,d,h);assert p.status_code==202,p.json
    with app.app_context():assert 'error' not in uploads.process_one()
    payload=repair_body(d['draftId']);payload['photoIds']=[p.json['data']['photoId']]
    r=client.post('/api/v1/requests',json=payload,headers=h|{'X-Draft-Token':d['draftToken'],'Idempotency-Key':str(uuid.uuid4())});assert r.status_code==201,r.json
    with app.app_context(),db.connect() as c:c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    restored=tmp_path.parent/(tmp_path.name+'-restored');shutil.copytree(tmp_path,restored)
    again=create_app(dict(app.config,DATA_DIR=str(restored)));token=r.json['data']['statusUrl'].split('#token=')[1]
    assert again.test_client().get('/api/v1/status',headers={'Authorization':'Bearer '+token}).status_code==200
    with again.app_context(),db.connect() as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        photo=c.execute('SELECT * FROM photos').fetchone();assert uploads.storage(photo['sanitized_key']).is_file()
