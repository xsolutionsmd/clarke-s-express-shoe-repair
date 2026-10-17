"""Private streaming uploads, slot reservations and serialized sandbox decoding."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from flask import Blueprint,current_app,g,request,send_file
from .core import ApiError,DAY,now,iso,uid,token,sha,digest,encrypt,decrypt,body,ok,row,replay,remember,key_required,fail,audit
from .db import connect,transaction
from .security import require_staff,limit,trusted_ip

bp=Blueprint('uploads',__name__)
MAX_FILE=10485760

def storage(key):
    import re
    if not isinstance(key,str) or not re.fullmatch(r'(quarantine|sanitized)/[0-9a-f-]{36}\.(raw|jpg|part)',key):raise ValueError('Invalid storage identity')
    root=Path(current_app.config['DATA_DIR'])/'uploads'
    path=root/key
    if path.is_symlink() or path.parent.is_symlink() or root.is_symlink():raise ValueError('Unsafe storage path')
    return path

def authorize_draft(c,ident,active=False):
    raw=request.headers.get('X-Draft-Token','')
    r=c.execute('SELECT * FROM drafts WHERE id=? AND token_hash=?',(ident,digest('draft',raw))).fetchone()
    if not r or r['state']=='deleted':raise ApiError('NOT_FOUND',404)
    if r['expires_at']<=now():raise ApiError('DRAFT_EXPIRED',409)
    if active and r['state']=='submitted':raise ApiError('DRAFT_SUBMITTED',409)
    return r

def photo_view(r):
    error=None
    if r['error_code']:
        error=dict(code=r['error_code'],message='This photo is too large to process. Export a smaller image.' if r['error_code']=='IMAGE_LIMIT_EXCEEDED' else 'This photo could not be read. Try another photo.')
    return dict(photoId=r['id'],state=r['state'],mediaType=r['media_type'],width=r['width'],height=r['height'],bytes=r['bytes'],error=error)

def draft_view(c,r):
    result=dict(draftId=r['id'],state=r['state'],expiresAt=iso(r['expires_at']),photos=[photo_view(p) for p in c.execute("SELECT * FROM photos WHERE draft_id=? AND state<>'deleted' ORDER BY slot",(r['id'],))])
    if r['state']=='submitted':result['receipt']=decrypt(r['receipt_cipher'])
    return result

def queue_delete(c,photo):
    if photo['state']=='deleted':return
    for key in (photo['raw_key'],photo['sanitized_key']):
        if key:c.execute('INSERT OR IGNORE INTO file_deletions(id,photo_id,storage_key,queued_at) VALUES(?,?,?,?)',(uid(),photo['id'],key,now()))
    c.execute("UPDATE photos SET state='deleted',deleted_at=? WHERE id=?",(now(),photo['id']))
    audit(c,'photo.deleted','photo',photo['id'])

@bp.post('/api/v1/drafts')
def create_draft():
    p=body(set())
    with transaction() as c:
        scope='session:'+sha(g.sid);prior=replay(c,scope,p)
        if prior:return prior
        limit(c,'draft',trusted_ip(),10,3600000)
        if c.execute("SELECT count(*) FROM drafts WHERE sid_hash=? AND state='active' AND expires_at>?",(sha(g.sid),now())).fetchone()[0]>=3:raise ApiError('RATE_LIMITED',429,details={'retryAfterSeconds':3600})
        ident,raw=uid(),token()
        c.execute("INSERT INTO drafts VALUES(?,?,?,?,?,'active',NULL,NULL)",(ident,digest('draft',raw),sha(g.sid),now(),now()+DAY))
        result=draft_view(c,row(c,'drafts',ident))|{'draftToken':raw}
        return remember(c,scope,p,result,201,ident)

@bp.route('/api/v1/drafts/<ident>',methods=['GET','DELETE'])
def draft(ident):
    with transaction() as c:
        r=authorize_draft(c,ident,request.method=='DELETE')
        if request.method=='GET':return ok(draft_view(c,r))
        for photo in c.execute("SELECT * FROM photos WHERE draft_id=? AND state<>'deleted'",(ident,)):queue_delete(c,photo)
        c.execute("UPDATE drafts SET state='deleted' WHERE id=?",(ident,))
        return ok(status=204)

def file_magic(header):
    if header.startswith(b'\xff\xd8\xff'):return True
    if header.startswith(b'\x89PNG\r\n\x1a\n'):return True
    if header[:4]==b'RIFF' and header[8:12]==b'WEBP':return True
    return len(header)>12 and header[4:8]==b'ftyp' and header[8:12] in (b'heic',b'heix',b'hevc',b'hevx',b'mif1')

@bp.post('/api/v1/drafts/<ident>/photos')
def upload(ident):
    key=key_required();scope='draft:'+ident
    if request.mimetype!='multipart/form-data':raise ApiError('UNSUPPORTED_MEDIA_TYPE',415)
    if request.content_length and request.content_length>11*1024*1024:raise ApiError('UPLOAD_TOO_LARGE',413)
    if shutil.disk_usage(current_app.config['DATA_DIR']).free<current_app.config['UPLOAD_MIN_FREE_BYTES']:raise ApiError('UPLOAD_CAPACITY',503,retryable=True)
    # Reserve before reading/parsing the multipart stream, preventing a sixth concurrent slot.
    with transaction() as c:
        authorize_draft(c,ident,True)
        existing=c.execute('SELECT * FROM idempotency WHERE actor_scope_hash=? AND route=? AND key_hash=?',(digest('actor',scope),request.path,key)).fetchone()
        if existing and existing['canonical_payload_hash'] is None:raise ApiError('IDEMPOTENCY_IN_PROGRESS',409,details={'retryAfterSeconds':2},retryable=True)
        if not existing:
            used={p[0] for p in c.execute("SELECT slot FROM photos WHERE draft_id=? AND state<>'deleted'",(ident,))}
            if len(used)>=5:fail('photoIds','You can attach up to five photos. Remove one to add another.')
            limit(c,'upload-files',trusted_ip(),30,3600000)
            photo_id=uid();raw_key='quarantine/'+photo_id+'.raw'
            c.execute("INSERT INTO photos(id,draft_id,state,slot,raw_key,created_at,lease_expires_at) VALUES(?,?,'uploading',?,?,?,?)",(photo_id,ident,min(set(range(5))-used),raw_key,now(),now()+300000))
            c.execute('INSERT INTO idempotency VALUES(?,?,?,NULL,NULL,NULL,?,?,?,0)',(digest('actor',scope),request.path,key,photo_id,now(),now()+7*DAY))
        else:photo_id=existing['entity_id'];raw_key='quarantine/'+uid()+'.raw'
    path=storage(raw_key);complete=False
    try:
        if set(request.files)!={'file'} or len(request.files.getlist('file'))!=1 or request.form:raise ApiError('UNSUPPORTED_MEDIA_TYPE',415)
        file=request.files['file'];total=0;hasher=hashlib.sha256();header=b''
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as output:
            while True:
                chunk=file.stream.read(65536)
                if not chunk:break
                total+=len(chunk)
                if total>MAX_FILE:raise ApiError('UPLOAD_TOO_LARGE',413)
                if len(header)<32:header=(header+chunk)[:32]
                hasher.update(chunk);output.write(chunk)
            output.flush();os.fsync(output.fileno())
        if not file_magic(header):raise ApiError('UNSUPPORTED_IMAGE',415)
        with transaction() as c:
            authorize_draft(c,ident,True)
            if existing:
                prior=replay(c,scope,hasher.hexdigest())
                return prior
            p=row(c,'photos',photo_id)
            if p['state']!='uploading':raise ApiError('DRAFT_EXPIRED',409)
            limit(c,'upload-bytes',trusted_ip(),200*1024*1024,3600000,total)
            c.execute("UPDATE photos SET state='processing',source_sha256=?,lease_expires_at=? WHERE id=?",(hasher.hexdigest(),now()+300000,photo_id))
            result=photo_view(row(c,'photos',photo_id))
            c.execute('UPDATE idempotency SET canonical_payload_hash=?,encrypted_response=?,status=202 WHERE actor_scope_hash=? AND route=? AND key_hash=?',(sha(json.dumps(hasher.hexdigest(),ensure_ascii=False,sort_keys=True,separators=(',',':'))),encrypt(result),digest('actor',scope),request.path,key))
        complete=True
        return ok(result,202)
    finally:
        if not complete:
            if path.exists() and not path.is_symlink():path.unlink()
            if not existing:
                with transaction() as c:
                    c.execute("UPDATE photos SET state='deleted',deleted_at=? WHERE id=? AND state='uploading'",(now(),photo_id))
                    c.execute('DELETE FROM idempotency WHERE actor_scope_hash=? AND route=? AND key_hash=? AND canonical_payload_hash IS NULL',(digest('actor',scope),request.path,key))

@bp.route('/api/v1/drafts/<ident>/photos/<photo_id>',methods=['GET','DELETE'])
def photo(ident,photo_id):
    with transaction() as c:
        authorize_draft(c,ident,request.method=='DELETE');p=row(c,'photos',photo_id)
        if p['draft_id']!=ident:raise ApiError('NOT_FOUND',404)
        if request.method=='GET':return ok(photo_view(p))
        if p['request_id']:raise ApiError('DRAFT_SUBMITTED',409)
        if p['state']!='deleted':queue_delete(c,p)
        return ok(status=204)

@bp.get('/api/v1/admin/requests/<ident>/photos/<photo_id>')
def private_photo(ident,photo_id):
    with connect() as c:
        require_staff(c=c);p=row(c,'photos',photo_id)
        if p['request_id']!=ident or p['state']!='ready' or not p['sanitized_key']:raise ApiError('PHOTO_UNAVAILABLE',404)
        try:fd=os.open(storage(p['sanitized_key']),os.O_RDONLY|os.O_NOFOLLOW)
        except OSError:raise ApiError('PHOTO_UNAVAILABLE',404) from None
    response=send_file(os.fdopen(fd,'rb'),mimetype='image/jpeg',download_name='repair-photo.jpg',etag=False,max_age=0)
    response.headers['Content-Disposition']='inline; filename="repair-photo.jpg"'
    return response

def convert(raw_key,output_key):
    source=os.open(storage(raw_key),os.O_RDONLY|os.O_NOFOLLOW)
    try:dest=os.open(storage(output_key),os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except Exception:
        os.close(source)
        raise
    try:
        with tempfile.TemporaryFile(mode='w+b',dir='/tmp') as result:
            try:
                run=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('decoder.py')),str(source),str(dest),str(result.fileno())],pass_fds=(source,dest,result.fileno()),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env={'PATH':'/usr/local/bin:/usr/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1'},timeout=20,close_fds=True)
                if run.returncode:return {'error':'IMAGE_LIMIT_EXCEEDED'}
                result.seek(0);return json.loads(result.read(4096))
            except subprocess.TimeoutExpired:return {'error':'IMAGE_LIMIT_EXCEEDED'}
            except (ValueError,OSError):return {'error':'IMAGE_INVALID'}
    finally:os.close(source);os.close(dest)

def process_one():
    folder=Path(current_app.config['DATA_DIR'])
    with open(folder/'decoder.lock','a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return None
        with transaction() as c:
            p=c.execute("SELECT * FROM photos WHERE state='processing' AND processing_lease IS NULL ORDER BY created_at LIMIT 1").fetchone()
            if not p:return None
            p=dict(p);lease=token()
            c.execute('UPDATE photos SET processing_lease=?,lease_expires_at=? WHERE id=?',(lease,now()+300000,p['id']))
        part='sanitized/'+p['id']+'.part';final='sanitized/'+p['id']+'.jpg'
        try:result=convert(p['raw_key'],part)
        except (OSError,ValueError):result={'error':'IMAGE_INVALID'}
        try:
            with transaction() as c:
                latest=row(c,'photos',p['id']);draft=row(c,'drafts',p['draft_id'])
                if latest['state']!='processing' or draft['state']!='active' or draft['expires_at']<=now():result={'error':'IMAGE_INVALID'}
                if 'error' not in result:
                    os.replace(storage(part),storage(final))
                    with open(storage(final),'rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
                    directory=os.open(storage(final).parent,os.O_RDONLY|os.O_DIRECTORY)
                    try:os.fsync(directory)
                    finally:os.close(directory)
                    c.execute("UPDATE photos SET state='ready',sanitized_key=?,raw_key=NULL,output_sha256=?,bytes=?,width=?,height=?,media_type='image/jpeg',ready_at=?,processing_lease=NULL WHERE id=?",(final,checksum,result['bytes'],result['width'],result['height'],now(),p['id']))
                elif latest['state']=='processing':
                    c.execute("UPDATE photos SET state='rejected',error_code=?,raw_key=NULL,processing_lease=NULL WHERE id=?",(result['error'],p['id']))
        finally:
            for key in (p['raw_key'],part):
                path=storage(key)
                if path.exists() and not path.is_symlink():path.unlink()
        return result
