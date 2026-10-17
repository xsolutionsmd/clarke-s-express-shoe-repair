"""Exercise every cursor consumer through its authenticated HTTP endpoint."""
import json
import pytest
from itsdangerous import TimestampSigner
from conftest import staff, repair_body
from clarke import core, db, repairs, validation


CASES=['inbox','outbox','audit','members','invitations','notices','events','notes','offers','public_events']


@pytest.fixture
def lists(app):
    admin,h,member=staff(app)
    with app.app_context(),db.transaction() as c:
        parent=repairs.create_record(c,validation.repair(repair_body('unused')),'online')
        other=repairs.create_record(c,validation.repair(repair_body('unused')),'online')
        token=core.decrypt(parent['status_token_cipher']);other_token=core.decrypt(other['status_token_cipher'])
    return admin,member,parent['id'],token,other['id'],other_token


def seed(app,case,member,parent,index):
    # Equal timestamps deliberately force the ID tie-breaker for every list.
    ident=f'{index:08d}-0000-4000-8000-000000000000'
    with app.app_context(),db.transaction() as c:
        if case=='inbox':
            r=repairs.create_record(c,validation.repair(repair_body('unused')),'online')
            c.execute("UPDATE requests SET id=?,created_at=1000,contact_name='Cursor fixture' WHERE id=?",(ident,r['id']))
        elif case=='members':
            c.execute("INSERT INTO members(id,email_norm,role,joined_at,updated_at) VALUES(?,?,'viewer',1000,1000)",(ident,f'cursor{index}@example.test'))
        elif case=='invitations':
            c.execute("INSERT INTO invitations(id,token_hash,email_norm,role,creator_id,created_at,expires_at) VALUES(?,?,?,'viewer',?,1000,?)",(ident,ident,f'invite{index}@example.test',member,core.now()+core.DAY))
        elif case=='notices':
            c.execute("INSERT INTO notices(id,locations,message,starts_at,ends_at,created_by,updated_by,created_at,updated_at) VALUES(?,'[\"bel_air\"]','Synthetic closure',0,?,?,?,1000,1000)",(ident,core.now()+core.DAY,member,member))
        elif case=='notes':
            c.execute("INSERT INTO notes VALUES(?,?,?,'Synthetic internal note',1000,1)",(ident,parent,member))
        elif case=='offers':
            c.execute("INSERT INTO offers(id,request_id,kind,state,scope,created_by,created_at) VALUES(?,?,'visit','superseded','Synthetic visit assessment',?,1000)",(ident,parent,member))
        elif case in ('events','public_events'):
            c.execute("INSERT INTO request_events(id,request_id,type,status,visibility,request_version,created_at) VALUES(?,?,'received','new','customer',1,1000)",(ident,parent))
        elif case=='outbox':
            c.execute("INSERT INTO outbox(id,event_key,event_id,request_id,kind,recipient_norm,subject,status,sender_generation,created_at,updated_at) VALUES(?,?,?,?,'customer_received','synthetic@example.test','Synthetic','preview_only',1,1000,1000)",(ident,ident,ident,parent))
        elif case=='audit':
            c.execute("INSERT INTO audit_events(id,actor_id,action,entity_type,entity_id,summary,created_at) VALUES(?,?,'cursor.fixture','request',?,'Synthetic',1000)",(ident,member,parent))
    return ident


def endpoint(case,parent):
    return {
        'inbox':('/api/v1/admin/requests',{'filter':'all','q':'Cursor fixture'}),
        'outbox':('/api/v1/admin/outbox',{'requestId':parent,'status':'preview_only'}),
        'audit':('/api/v1/admin/audit',{'requestId':parent,'action':'cursor.fixture'}),
        'members':('/api/v1/admin/team/members',{}),
        'invitations':('/api/v1/admin/team/invitations',{'state':'pending'}),
        'notices':('/api/v1/admin/notices',{'state':'active','location':'bel_air'}),
        'public_events':('/api/v1/status/events',{}),
    }.get(case,('/api/v1/admin/requests/'+parent+'/'+case,{}))


@pytest.mark.parametrize('case',CASES)
def test_all_lists_keysets_survive_insert_and_boundary_removal(app,lists,case):
    admin,member,parent,token,_,_=lists
    expected=[seed(app,case,member,parent,i) for i in range(1,7)][::-1]
    path,query=endpoint(case,parent);headers={'Authorization':'Bearer '+token}
    # Members includes the real fixture admins; keep those before the fixture rows.
    first=admin.get(path,query_string=query | {'limit':2},headers=headers)
    assert first.status_code==200,first.json
    data=first.json['data'];seen=[r['id'] for r in data['items']]
    cursor=data['nextCursor'];assert cursor
    seed(app,case,member,parent,9)  # Insert ahead of the saved boundary.
    boundary=seen[-1]
    table={'inbox':'requests','public_events':'request_events','events':'request_events','audit':'audit_events'}.get(case,case)
    # Don't delete a signed-in staff fixture; the next page still tests insertion.
    if case!='members':
        with app.app_context(),db.transaction() as c:c.execute(f'DELETE FROM {table} WHERE id=?',(boundary,))
    while cursor:
        r=admin.get(path,query_string=query | {'limit':2,'cursor':cursor},headers=headers)
        assert r.status_code==200,r.json
        data=r.json['data'];seen.extend(x['id'] for x in data['items']);cursor=data['nextCursor']
    assert len(seen)==len(set(seen))
    if case=='members':
        # The newly inserted ID is below the admins but ahead of fixture rows;
        # it is legitimately encountered after that earlier boundary.
        assert [x for x in seen if x in expected]==expected
    else:assert seen==expected


@pytest.mark.parametrize('case',CASES)
def test_all_cursors_expire_at_thirty_minutes_and_bind_principal_resource(app,lists,monkeypatch,case):
    admin,member,parent,token,other,other_token=lists
    for i in range(1,5):seed(app,case,member,parent,i)
    path,query=endpoint(case,parent);headers={'Authorization':'Bearer '+token}
    start=core.now()//1000
    monkeypatch.setattr(TimestampSigner,'get_timestamp',lambda self:start)
    first=admin.get(path,query_string=query | {'limit':1},headers=headers).json['data']
    cursor=first['nextCursor'];assert cursor
    params=query | {'limit':1,'cursor':cursor}
    if case=='public_events':
        wrong=admin.get(path,query_string=params,headers={'Authorization':'Bearer '+other_token})
    else:
        another,_,_=staff(app)
        wrong=another.get(path,query_string=params)
    assert wrong.status_code==400 and wrong.json['error']['code']=='INVALID_CURSOR'
    if case in ('events','notes','offers'):
        assert admin.get(path.replace(parent,other),query_string=params).status_code==400
    monkeypatch.setattr(TimestampSigner,'get_timestamp',lambda self:start+1800)
    assert admin.get(path,query_string=params,headers=headers).status_code==200
    monkeypatch.setattr(TimestampSigner,'get_timestamp',lambda self:start+1801)
    expired=admin.get(path,query_string=params,headers=headers)
    assert expired.status_code==400 and expired.json['error']['code']=='INVALID_CURSOR'


@pytest.mark.parametrize('case,changes',[
    ('inbox',[{'filter':'closed'},{'q':'Different name'},{'location':'dundalk'},{'status':'not_repairable'}]),
    ('outbox',[{'status':'failed'},{'requestId':'another'}]),
    ('audit',[{'action':'other'},{'actorId':'another'},{'requestId':'another'}]),
    ('invitations',[{'state':'expired'}]),('notices',[{'state':'expired'},{'location':'dundalk'}]),
])
def test_filter_bound_cursors(app,lists,case,changes):
    admin,member,parent,_,_,_=lists
    for i in range(1,4):seed(app,case,member,parent,i)
    path,query=endpoint(case,parent)
    cursor=admin.get(path,query_string=query | {'limit':1}).json['data']['nextCursor']
    for change in changes:
        response=admin.get(path,query_string=query | change | {'cursor':cursor})
        assert response.status_code==400 and response.json['error']['code']=='INVALID_CURSOR'


def test_inbox_priority_and_status_exit_with_normalized_query(app,lists):
    admin,member,parent,_,_,_=lists
    ids=[seed(app,'inbox',member,parent,i) for i in range(1,7)]
    with app.app_context(),db.transaction() as c:
        c.execute("UPDATE requests SET status='reviewing',created_at=999999 WHERE id IN (?,?)",ids[4:])
    path='/api/v1/admin/requests';query={'filter':'new','q':' Cursor fixture '}
    first=admin.get(path,query_string=query | {'limit':2}).json['data']
    assert [x['id'] for x in first['items']]==[ids[3],ids[2]]
    with app.app_context(),db.transaction() as c:
        c.execute("UPDATE requests SET status='ready' WHERE id=?",(ids[2],))
    rest=admin.get(path,query_string={'filter':'new','q':'cursor fixture','cursor':first['nextCursor']}).json['data']
    assert [x['id'] for x in rest['items']]==[ids[1],ids[0],ids[5],ids[4]]


@pytest.mark.parametrize('case',['invitations','notices','outbox'])
def test_filtered_lists_remove_boundary_by_state_change(app,lists,case):
    admin,member,parent,_,_,_=lists
    ids=[seed(app,case,member,parent,i) for i in range(1,5)]
    path,query=endpoint(case,parent)
    first=admin.get(path,query_string=query | {'limit':2}).json['data']
    with app.app_context(),db.transaction() as c:
        update={'invitations':'revoked_at=1','notices':'deleted_at=1','outbox':"status='cancelled'"}[case]
        c.execute(f'UPDATE {case} SET {update} WHERE id=?',(ids[2],))
    rest=admin.get(path,query_string=query | {'cursor':first['nextCursor']}).json['data']
    assert [x['id'] for x in rest['items']]==ids[:2][::-1]
