import io
from pathlib import Path
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from PIL import Image
from conftest import draft,upload,image_bytes,headers,repair_body,staff
from clarke import uploads,core,db,maintenance

@pytest.mark.parametrize('format',['JPEG','PNG','WEBP'])
def test_conversion_metadata_sandbox_and_private_access(app,client,format):
    d,h=draft(client);response=upload(client,d,h,image_bytes(format),'renamed.any');assert response.status_code==202,response.json
    with app.app_context():
        result=uploads.process_one();assert 'error' not in result,result
        assert result['sandboxFileDenied'] and result['sandboxNetworkDenied'] and result['sandboxProcessDenied']
        with db.connect() as c:
            photo=dict(c.execute('SELECT * FROM photos').fetchone());assert photo['raw_key'] is None
            with Image.open(uploads.storage(photo['sanitized_key'])) as image:
                assert image.format=='JPEG' and not image.getexif() and not set(image.info)&{'xmp','icc_profile','comment','exif'}
    poll=client.get(f"/api/v1/drafts/{d['draftId']}/photos/{photo['id']}",headers={'X-Draft-Token':d['draftToken']})
    assert poll.json['data']['state']=='ready' and 'url' not in poll.json['data']
    p=repair_body(d['draftId']);p['photoIds']=[photo['id']]
    created=client.post('/api/v1/requests',json=p,headers=h|{'X-Draft-Token':d['draftToken'],'Idempotency-Key':str(uuid.uuid4())});assert created.status_code==201,created.json
    with app.app_context(),db.connect() as c:ident=c.execute('SELECT id FROM requests').fetchone()[0]
    path=f"/api/v1/admin/requests/{ident}/photos/{photo['id']}"
    assert client.get(path).status_code==401
    viewer,_,_=staff(app,'viewer');r=viewer.get(path);assert r.status_code==200 and r.mimetype=='image/jpeg'
    assert viewer.get(f'/api/v1/admin/requests/{uuid.uuid4()}/photos/'+photo['id']).status_code==404

def test_type_size_count_partial_upload_and_expiry(app,client):
    d,h=draft(client)
    assert upload(client,d,h,b'<svg/>','test.jpg').status_code==415
    assert upload(client,d,h,b'\xff\xd8\xff'+b'x'*(10485760),'large.jpg').status_code==413
    ids=[]
    for _ in range(5):
        r=upload(client,d,h);assert r.status_code==202,r.json;ids.append(r.json['data']['photoId'])
    assert upload(client,d,h).status_code==422
    p=repair_body(d['draftId']);p['photoIds']=ids
    assert client.post('/api/v1/requests',json=p,headers=h|{'X-Draft-Token':d['draftToken'],'Idempotency-Key':str(uuid.uuid4())}).json['error']['code']=='PHOTOS_NOT_READY'
    assert client.delete(f"/api/v1/drafts/{d['draftId']}/photos/{ids[0]}",headers=h|{'X-Draft-Token':d['draftToken']}).status_code==204
    with app.app_context(),db.transaction() as c:c.execute('UPDATE drafts SET expires_at=? WHERE id=?',(core.now()-1,d['draftId']))
    assert client.get('/api/v1/drafts/'+d['draftId'],headers={'X-Draft-Token':d['draftToken']}).json['error']['code']=='DRAFT_EXPIRED'
    with app.app_context():
        maintenance.reconcile()
        assert not list((Path(app.config['DATA_DIR'])/'uploads/quarantine').iterdir())

def test_sixth_slot_concurrency_and_replay(app,client):
    d,h=draft(client)
    for _ in range(4):assert upload(client,d,h).status_code==202
    cookie=client.get_cookie('clarke_session').value
    def last(_):
        c=app.test_client();c.set_cookie('clarke_session',cookie);return upload(c,d,h)
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(last,range(2)))
    assert sorted(x.status_code for x in results)==[202,422]
    with app.app_context(),db.connect() as c:assert c.execute("SELECT count(*) FROM photos WHERE state<>'deleted'").fetchone()[0]==5

def test_corrupt_animated_pixel_limits_and_stale_cleanup(app,client):
    d,h=draft(client)
    animated=io.BytesIO();frames=[Image.new('RGB',(24,24),color) for color in ('red','blue')];frames[0].save(animated,format='WEBP',save_all=True,append_images=frames[1:])
    for data in (b'\xff\xd8\xffcorrupt',animated.getvalue()):
        r=upload(client,d,h,data)
        assert r.status_code==202
        with app.app_context():assert uploads.process_one()['error']=='IMAGE_INVALID'
    with app.app_context(),db.transaction() as c:
        c.execute("UPDATE photos SET state='processing',processing_lease='interrupted',lease_expires_at=?",(core.now()-1,))
    with app.app_context():
        maintenance.reconcile()
        with db.connect() as c:assert {r[0] for r in c.execute('SELECT state FROM photos')}=={'rejected'}

def test_real_12mp_heic_under_runtime_limit(app,client):
    fixture=Path('/opt/test-fixtures/phone-12mp.heic')
    assert fixture.exists(),'The backend-test build must generate a real 4032×3024 HEIC fixture.'
    d,h=draft(client);r=upload(client,d,h,fixture.read_bytes(),'phone.heic');assert r.status_code==202,r.json
    with app.app_context():
        result=uploads.process_one();assert 'error' not in result,result
        assert max(result['width'],result['height'])==2048 and result['peakRssKiB']<160*1024
        assert result['sandboxFileDenied'] and result['sandboxNetworkDenied']
        with db.connect() as c:
            photo=c.execute('SELECT * FROM photos').fetchone()
            with Image.open(uploads.storage(photo['sanitized_key'])) as im:assert not im.getexif() and 'icc_profile' not in im.info

def test_photo_retention_and_synthetic_purge(app,client):
    from conftest import submit,identify
    receipt,_,_=submit(client);ident=identify(app,receipt)
    with app.app_context():
        with pytest.raises(ValueError):maintenance.purge_synthetic([ident])
        with db.transaction() as c:c.execute('UPDATE requests SET is_synthetic=1 WHERE id=?',(ident,))
        maintenance.purge_synthetic([ident])
        with db.connect() as c:
            assert c.execute('SELECT count(*) FROM requests').fetchone()[0]==0
            assert c.execute('SELECT count(*) FROM outbox').fetchone()[0]==0
            assert c.execute("SELECT count(*) FROM audit_events WHERE action='synthetic.purged'").fetchone()[0]==1
