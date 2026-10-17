"""HTTP probe for a credential-free candidate, replacement and complete-volume restore."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import uuid
import requests
from PIL import Image
import seed_sessions

BASE='http://candidate:8080'
RECEIPT=Path('/data/api-probe.json')
s=requests.Session()

def api(method,path,payload=None,**kwargs):
    headers=kwargs.pop('headers',{})
    if method!='GET':
        bootstrap=s.get(BASE+'/api/v1/bootstrap',timeout=15);bootstrap.raise_for_status()
        headers.update({'Origin':BASE,'X-CSRF-Token':bootstrap.json()['data']['csrfToken'],'Idempotency-Key':str(uuid.uuid4())})
    r=s.request(method,BASE+path,json=payload,headers=headers,timeout=30,**kwargs)
    assert r.status_code<400,(method,path,r.status_code,r.json().get('error',{}).get('code'))
    return r.json()['data'] if r.content else None

def files():
    with seed_sessions.database() as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        photo=c.execute("SELECT * FROM photos WHERE id=(SELECT value FROM app_meta WHERE key='probe_photo')").fetchone()
        assert photo['state']=='ready' and not photo['raw_key']
    paths=['secret.key','encryption.key','uploads/'+photo['sanitized_key']]
    return {p:hashlib.sha256((Path('/data')/p).read_bytes()).hexdigest() for p in paths}

def verify(data):
    assert s.get(BASE+'/health',timeout=10).json()=={'status':'ok'}
    assert s.get(BASE+'/version.json',timeout=10).json()['revision']==os.environ['APP_REVISION']
    assert api('GET','/api/v1/bootstrap')['googleReady'] is False
    raw=data['receipt']['statusUrl'].split('#token=')[1]
    public=api('GET','/api/v1/status',headers={'Authorization':'Bearer '+raw})
    assert public['reference']==data['receipt']['reference'] and 'contact' not in public
    s.cookies.clear();s.cookies.set('clarke_session',data['admin']['cookie']['value'],path='/')
    detail=api('GET','/api/v1/admin/requests/'+data['id'])
    assert len(detail['photos'])==1 and detail['contact']['name']=='Synthetic Runtime Probe'
    r=s.get(BASE+'/api/v1/admin/requests/'+data['id']+'/photos/'+data['photo'],timeout=15)
    assert r.status_code==200 and r.headers['X-Robots-Tag']=='noindex, nofollow'
    with Image.open(io.BytesIO(r.content)) as im:
        assert max(im.size)==2048 and not im.getexif() and 'icc_profile' not in im.info
    assert files()==data['hashes']
    assert {r['status'] for r in api('GET','/api/v1/admin/outbox')['items']}=={'preview_only'}

if sys.argv[1]=='create':
    assert s.get(BASE+'/api/v1/admin/session',timeout=10).status_code==401
    assert api('GET','/api/v1/bootstrap')['googleReady'] is False
    d=api('POST','/api/v1/drafts',{})
    h={'X-Draft-Token':d['draftToken']}
    with open('/opt/test-fixtures/phone-12mp.heic','rb') as source:
        photo=api('POST','/api/v1/drafts/'+d['draftId']+'/photos',headers=h,files={'file':('phone.heic',source,'image/heic')})['photoId']
    deadline=time.monotonic()+30
    while True:
        state=api('GET','/api/v1/drafts/'+d['draftId']+'/photos/'+photo,headers=h)
        if state['state'] not in ('processing','uploading'):break
        assert time.monotonic()<deadline
        time.sleep(.3)
    assert state['state']=='ready',state
    p=dict(draftId=d['draftId'],itemType='boots',workTypes=['soles_heels'],description='Synthetic real HTTP probe for complete persistence.',brandAge=None,location='dundalk',neededBy=None,contact=dict(name='Synthetic Runtime Probe',email='probe@example.test',phone=None,preferred='email'),photoIds=[photo],consentVersion='repair-intake-v1',website='')
    receipt=api('POST','/api/v1/requests',p,headers=h)
    admin=seed_sessions.seed()
    with seed_sessions.database() as c:
        ident=c.execute('SELECT id FROM requests').fetchone()[0]
        c.execute('UPDATE requests SET is_synthetic=1 WHERE id=?',(ident,))
        c.execute("INSERT INTO app_meta VALUES('probe_photo',?)",(photo,))
    data=dict(receipt=receipt,id=ident,photo=photo,admin=admin,hashes=files())
    RECEIPT.write_text(json.dumps(data));os.chmod(RECEIPT,0o600)
else:
    data=json.loads(RECEIPT.read_text())
verify(data)
print('PASS: HTTP HEIC/private-photo/status/outbox/health/revision and complete data-key hashes ('+sys.argv[1]+').')
