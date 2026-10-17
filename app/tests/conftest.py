import io
import json
import secrets
from pathlib import Path
import sys
import uuid
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import create_app
from clarke import core,db,security

ORIGIN='http://candidate:8080'

@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DATA_DIR':str(tmp_path),'PUBLIC_ORIGIN':ORIGIN,'INITIAL_ADMIN_EMAIL':'first@example.test','NOTIFICATION_EMAILS':{'alerts@example.test'},'DEMO_ALLOWED_EMAILS':{'allowed@example.test'},'DEMO_ALLOWED_PHONES':{'+12025550123'},'GOOGLE_CLIENT_ID':'synthetic-client','GOOGLE_CLIENT_SECRET':'synthetic-secret','UPLOAD_MIN_FREE_BYTES':0})

@pytest.fixture
def client(app):return app.test_client()

def headers(client,**extra):
    token=client.get('/api/v1/bootstrap').json['data']['csrfToken']
    return {'Origin':ORIGIN,'X-CSRF-Token':token,'Idempotency-Key':str(uuid.uuid4())}|extra

def staff(app,role='admin',address=None,expired=False):
    address=address or role+'-'+uuid.uuid4().hex[:6]+'@example.test';ident=str(uuid.uuid4());sid=secrets.token_urlsafe(32)
    with app.app_context():
        stamp=core.now();csrf=security.csrf_for(sid)
        with db.transaction() as c:
            c.execute('INSERT INTO members VALUES(?,?,?,?,1,1,?,?,?)',(ident,address,'synthetic-'+ident,role,stamp,stamp,stamp))
            c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,NULL,?)',(core.sha(sid),core.sha(csrf),ident,1,stamp,stamp,stamp-1 if expired else stamp+43200000,stamp-1 if expired else stamp+7200000,'google'))
        signed=app.extensions['sessions'].dumps({'sid':sid})
    client=app.test_client();client.set_cookie('clarke_session',signed)
    return client,{'Origin':ORIGIN,'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid.uuid4())},ident

def draft(client):
    h=headers(client);r=client.post('/api/v1/drafts',json={},headers=h)
    assert r.status_code==201,r.json
    return r.json['data'],h

def repair_body(draft_id,email=None):
    return dict(draftId=draft_id,itemType='boots',workTypes=['soles_heels'],description='The left boot heel has separated from the sole.',brandAge=None,location='bel_air',neededBy=None,contact=dict(name='Synthetic Customer',email=email or uuid.uuid4().hex[:8]+'@example.test',phone=None,preferred='email'),photoIds=[],consentVersion='repair-intake-v1',website='')

def submit(client,**changes):
    d,h=draft(client);h['X-Draft-Token']=d['draftToken'];h['Idempotency-Key']=str(uuid.uuid4());p=repair_body(d['draftId']);p.update(changes)
    r=client.post('/api/v1/requests',json=p,headers=h)
    assert r.status_code==201,r.json
    return r.json['data'],p,h

def identify(app,receipt):
    with app.app_context(),db.connect() as c:return c.execute('SELECT id FROM requests WHERE reference_hash=?',(core.digest('reference',receipt['reference'].replace('-','')[3:]),)).fetchone()[0]

def image_bytes(fmt='JPEG',size=(96,72)):
    output=io.BytesIO();image=Image.new('RGB',size,(88,42,33));exif=Image.Exif();exif[0x010E]='private source description';exif[0x013B]='private author'
    image.save(output,format=fmt,exif=exif);return output.getvalue()

def upload(client,d,h,data=None,name='shoe.jpg'):
    return client.post('/api/v1/drafts/'+d['draftId']+'/photos',data={'file':(io.BytesIO(data or image_bytes()),name)},headers=h|{'X-Draft-Token':d['draftToken'],'Idempotency-Key':str(uuid.uuid4())})
