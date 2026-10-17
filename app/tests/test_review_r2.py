"""Regressions for the independently reproduced backend review findings."""
from datetime import datetime
import uuid
import pytest
from conftest import draft, repair_body, staff, submit, identify
from clarke import core, db, mail, validation
from test_mail import connected, Response


def fresh(headers):
    return headers | {'Idempotency-Key': str(uuid.uuid4())}


@pytest.mark.parametrize('online', [True, False])
def test_midnight_replay_precedes_new_action_date_check(app, client, monkeypatch, online):
    before = int(datetime.fromisoformat('2026-10-18T03:59:59+00:00').timestamp()*1000)
    monkeypatch.setattr(validation, 'now', lambda: before)
    if online:
        d, h = draft(client)
        h['X-Draft-Token'] = d['draftToken']
        p = repair_body(d['draftId'])
        path = '/api/v1/requests'
    else:
        client, h, member = staff(app)
        p = {k:v for k,v in repair_body('unused').items() if k in {'itemType','workTypes','description','brandAge','location','neededBy','contact'}}
        path = '/api/v1/admin/requests'
    p['neededBy'] = '2026-10-17'
    first = client.post(path, json=p, headers=h)
    assert first.status_code == 201, first.json
    monkeypatch.setattr(validation, 'now', lambda: before+2000)
    again = client.post(path, json=p, headers=h)
    assert again.status_code == 200 and again.json == first.json
    assert again.headers['Idempotency-Replayed'] == 'true'
    changed = client.post(path, json=p | {'description':'An intentionally changed repair description.'}, headers=h)
    assert changed.status_code == 409 and changed.json['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    for malformed in ({'neededBy':'not-a-date'}, {'contact':{}}, {'unknown':True}):
        assert client.post(path,json=p | malformed,headers=h).status_code == 422
    if online:
        assert client.post(path,json=p,headers=fresh(h)).json == first.json
        assert client.post(path,json=p,headers=h | {'X-Draft-Token':'wrong'}).status_code == 404
        other, oh = draft(client)
        assert client.post(path,json=p | {'draftId':other['draftId']},headers=oh | {'X-Draft-Token':other['draftToken']}).status_code == 422
        with app.app_context(), db.transaction() as c:
            c.execute('UPDATE drafts SET expires_at=? WHERE id=?',(core.now()-1,d['draftId']))
        assert client.post(path,json=p,headers=h).json['error']['code'] == 'DRAFT_EXPIRED'
    else:
        assert client.post(path,json=p,headers=fresh(h)).status_code == 422
        with app.app_context(), db.transaction() as c:
            c.execute('UPDATE sessions SET absolute_expires_at=? WHERE member_id=?',(core.now()-1,member))
        assert client.post(path,json=p,headers=h).status_code == 401
        with app.app_context(), db.transaction() as c:
            c.execute('UPDATE sessions SET absolute_expires_at=? WHERE member_id=?',(core.now()+60000,member))
            c.execute('UPDATE members SET active=0 WHERE id=?',(member,))
        assert client.post(path,json=p,headers=h).status_code == 401
    with app.app_context(), db.connect() as c:
        assert c.execute('SELECT count(*) FROM requests').fetchone()[0] == 1
        assert c.execute('SELECT count(*) FROM outbox').fetchone()[0] == 2


@pytest.mark.parametrize('delivery_state', ['pending','retry_wait','failed','uncertain','sent'])
def test_ready_edits_preserve_one_notification_and_retry(app,client,monkeypatch,delivery_state):
    connected(app)
    receipt,_,_ = submit(client, contact=dict(name='Allowed synthetic',email='allowed@example.test',phone=None,preferred='email'))
    ident = identify(app,receipt)
    admin,h,_ = staff(app)
    path = '/api/v1/admin/requests/'+ident
    ready = admin.patch(path,json=dict(expectedVersion=1,status='ready',pickupLocation='bel_air'),headers=fresh(h))
    assert ready.status_code == 200, ready.json
    notification = ready.json['data']['notificationEventIds'][0]
    with app.app_context(), db.transaction() as c:
        c.execute("UPDATE outbox SET status='sent' WHERE kind='customer_received'")
        c.execute('UPDATE outbox SET status=? WHERE id=?',(delivery_state,notification))
    for version, change in [(2,{'customerMessage':'A harmless message clarification.'}), (3,{'dropoffLocation':'dundalk'}), (4,{'status':'ready','pickupLocation':'bel_air','customerMessage':'Updated collection instructions.'})]:
        r=admin.patch(path,json={'expectedVersion':version} | change,headers=fresh(h))
        assert r.status_code == 200 and r.json['data']['notificationEventIds'] == [], r.json
    assert admin.post(path+'/notes',json=dict(expectedVersion=5,text='Internal collection note.'),headers=fresh(h)).status_code == 201
    with app.app_context(), db.connect() as c:
        rows=c.execute("SELECT * FROM outbox WHERE request_id=? AND kind='customer_ready'",(ident,)).fetchall()
        assert len(rows)==1 and rows[0]['id']==notification and rows[0]['status']==delivery_state
        assert mail.current_event(c,rows[0])
    view=admin.get('/api/v1/admin/outbox/'+notification).json['data']
    if delivery_state in ('failed','uncertain','retry_wait'):
        assert view['canRetry']
        assert admin.post('/api/v1/admin/outbox/'+notification+'/retry',json=dict(expectedVersion=view['version'],acknowledgePossibleDuplicate=True),headers=fresh(h)).status_code==202
    calls=[]
    monkeypatch.setattr(mail.requests,'post',lambda *a,**kw: calls.append(a) or Response())
    with app.app_context():
        mail.drain_one();mail.drain_one()
    assert len(calls)==(0 if delivery_state=='sent' else 1)


@pytest.mark.parametrize('change', ['pickup','status'])
@pytest.mark.parametrize('delivery_state', ['pending','retry_wait','failed','uncertain'])
def test_ready_actual_supersession_cancels_or_disables_retry(app,client,change,delivery_state):
    connected(app)
    receipt,_,_=submit(client,contact=dict(name='Allowed synthetic',email='allowed@example.test',phone=None,preferred='email'))
    ident=identify(app,receipt);admin,h,_=staff(app);path='/api/v1/admin/requests/'+ident
    ready=admin.patch(path,json=dict(expectedVersion=1,status='ready',pickupLocation='bel_air'),headers=fresh(h)).json['data']
    old=ready['notificationEventIds'][0]
    with app.app_context(), db.transaction() as c:c.execute('UPDATE outbox SET status=? WHERE id=?',(delivery_state,old))
    payload=dict(expectedVersion=2,pickupLocation='dundalk') if change=='pickup' else dict(expectedVersion=2,status='picked_up')
    result=admin.patch(path,json=payload,headers=fresh(h))
    assert result.status_code==200
    assert len(result.json['data']['notificationEventIds'])==(1 if change=='pickup' else 0)
    with app.app_context(), db.connect() as c:
        rows=c.execute("SELECT * FROM outbox WHERE request_id=? AND kind='customer_ready'",(ident,)).fetchall()
        oldrow=next(x for x in rows if x['id']==old)
        assert not mail.current_event(c,oldrow)
        assert oldrow['status']==('cancelled' if delivery_state in ('pending','retry_wait') else delivery_state)
        assert sum(mail.current_event(c,x) for x in rows)==(1 if change=='pickup' else 0)
    view=admin.get('/api/v1/admin/outbox/'+old).json['data']
    assert not view['canRetry']
    assert admin.post('/api/v1/admin/outbox/'+old+'/retry',json=dict(expectedVersion=view['version'],acknowledgePossibleDuplicate=True),headers=fresh(h)).json['error']['code']=='EMAIL_NOT_RETRYABLE'


@pytest.mark.parametrize('source,kind', [('not_repairable','visit'),('not_repairable','estimate'),('ready','estimate'),('ready','visit'),('picked_up','visit'),('needs_visit','estimate')])
def test_offers_require_reasoned_backward_patch_first(app,client,source,kind):
    receipt,_,_=submit(client);ident=identify(app,receipt);admin,h,_=staff(app);path='/api/v1/admin/requests/'+ident
    with app.app_context(), db.transaction() as c:
        c.execute('UPDATE requests SET status=?,closed_at=? WHERE id=?',(source,core.now() if source=='picked_up' else None,ident))
    offer=dict(expectedVersion=1,kind=kind,scope='Inspect the synthetic repair in the shop.',amountMinCents=1234 if kind=='estimate' else None,amountMaxCents=None)
    rejected=admin.post(path+'/offers',json=offer,headers=h)
    assert rejected.status_code==409 and rejected.json['error']['code']=='INVALID_TRANSITION'
    with app.app_context(), db.connect() as c:
        assert c.execute('SELECT version,status FROM requests WHERE id=?',(ident,)).fetchone()[:]==(1,source)
        assert c.execute('SELECT count(*) FROM offers').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM outbox').fetchone()[0]==2
    assert admin.patch(path,json=dict(expectedVersion=1,status='reviewing'),headers=fresh(h)).status_code==422
    assert admin.patch(path,json=dict(expectedVersion=1,status='reviewing',reason='Customer requested a fresh assessment.'),headers=fresh(h)).status_code==200
    accepted=admin.post(path+'/offers',json=offer | {'expectedVersion':2},headers=h)
    assert accepted.status_code==201, accepted.json
    assert admin.post(path+'/offers',json=offer | {'expectedVersion':2},headers=h).json==accepted.json


@pytest.mark.parametrize('kind',['estimate','visit'])
def test_forward_offer_and_same_kind_replacement_still_work(app,client,kind):
    receipt,_,_=submit(client);ident=identify(app,receipt);admin,h,_=staff(app)
    p=dict(expectedVersion=1,kind=kind,scope='Inspect the synthetic repair in the shop.',amountMinCents=1234 if kind=='estimate' else None)
    for v in (1,2):
        response=admin.post('/api/v1/admin/requests/'+ident+'/offers',json=p | {'expectedVersion':v},headers=fresh(h))
        assert response.status_code==201,response.json
