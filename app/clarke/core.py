"""Small shared primitives. No transport or fixture shortcuts live here."""
import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from flask import current_app, g, jsonify, request

DAY = 86_400_000
STATUSES = {'new':'Received','reviewing':'Being reviewed','estimate_sent':'Estimate ready','needs_visit':'Please bring it in','not_repairable':"We can't repair this",'awaiting_dropoff':'Waiting for drop-off','in_shop':'In the shop','in_progress':'Being repaired','ready':'Ready for pickup','picked_up':'Picked up','cancelled':'Closed'}
CLOSED = {'picked_up','cancelled'}
LOCATIONS = {'bel_air','dundalk'}
DISCLAIMER = 'Estimate; final price confirmed when we see the item in person.'

def now():
    return int(time.time() * 1000)

def uid():
    return str(uuid.uuid4())

def token():
    return secrets.token_urlsafe(32)

def iso(value):
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z') if value is not None else None

def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'))

def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()

def digest(domain, value):
    return hmac.new(current_app.secret_key, (domain+'\0'+value).encode(), hashlib.sha256).hexdigest()

def encrypt(value):
    return current_app.extensions['cipher'].encrypt(dumps(value).encode()).decode()

def decrypt(value):
    return json.loads(current_app.extensions['cipher'].decrypt(value.encode()))

class ApiError(Exception):
    def __init__(self, code, status=422, message=None, fields=None, details=None, retryable=False):
        self.code, self.status = code, status
        messages = {'STATUS_UNAVAILABLE':'This request is unavailable. Check your details or call the shop.', 'AUTH_REQUIRED':'Sign in to continue.', 'SESSION_EXPIRED':'Your session expired. Sign in again; your draft is kept.', 'FORBIDDEN':'Admin access is required.', 'VERSION_CONFLICT':'Updated by someone else. Reload the latest details; your draft is kept.', 'VALIDATION_FAILED':'Please check the highlighted fields.', 'DATABASE_BUSY':'The shop is busy saving another update. Try again; your draft is kept.', 'CSRF_INVALID':'Refresh your session and try again; your draft is kept.', 'RATE_LIMITED':'Please wait before trying again, or call the shop.', 'PHOTOS_NOT_READY':'Wait for your photos, or remove the rejected photo before submitting.', 'INTAKE_PAUSED':'Online requests are paused. Please call or text the shop.'}
        self.message = message or messages.get(code, code.replace('_',' ').capitalize()+'.')
        self.fields, self.details, self.retryable = fields or {}, details, retryable
        super().__init__(code)

def fail(field, message='Check this field.'):
    raise ApiError('VALIDATION_FAILED',fields={field:message})

def ok(data=None, status=200):
    if status == 204:
        return '', 204
    return jsonify(data=data), status

def body(allowed):
    if request.mimetype != 'application/json':
        raise ApiError('UNSUPPORTED_MEDIA_TYPE',415)
    if request.content_length and request.content_length > 32768:
        raise ApiError('UPLOAD_TOO_LARGE',413)
    raw=request.stream.read(32769)
    if len(raw)>32768:raise ApiError('UPLOAD_TOO_LARGE',413)
    def unique_pairs(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate JSON field')
            result[key]=value
        return result
    try:data=json.loads(raw,object_pairs_hook=unique_pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError,UnicodeError):raise ApiError('MALFORMED_JSON',400) from None
    if not isinstance(data,dict):
        raise ApiError('MALFORMED_JSON',400)
    if set(data)-set(allowed):
        fail(next(iter(set(data)-set(allowed))), 'This field is not accepted.')
    return data

def row(c, table, ident):
    # Table names come only from internal literal callers.
    found = c.execute(f'SELECT * FROM {table} WHERE id=?',(ident,)).fetchone()
    if not found:
        raise ApiError('NOT_FOUND',404)
    return found

def version(p, r, url=None):
    if 'expectedVersion' not in p:
        raise ApiError('VERSION_REQUIRED',428)
    if type(p['expectedVersion']) is not int:
        fail('expectedVersion')
    if p['expectedVersion'] != r['version']:
        raise ApiError('VERSION_CONFLICT',409,details={'expectedVersion':p['expectedVersion'],'currentVersion':r['version'],'resourceUrl':url or request.path})

def audit(c, action, entity, ident, before=None, after=None, summary=None):
    c.execute('INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?,?)',(uid(),getattr(g,'member',None)['id'] if getattr(g,'member',None) else None,action,entity,ident,before,after,summary or action.replace('.',' ').replace('_',' '),now()))

def key_required():
    key = request.headers.get('Idempotency-Key','')
    try:
        parsed = uuid.UUID(key)
        if parsed.version != 4 or str(parsed) != key.lower():
            raise ValueError()
    except (ValueError,AttributeError):
        raise ApiError('INVALID_IDEMPOTENCY_KEY',400) from None
    return sha(key)

def replay(c, scope, payload):
    key = key_required()
    scope_hash, payload_hash = digest('actor',scope), sha(dumps(payload))
    r = c.execute('SELECT * FROM idempotency WHERE actor_scope_hash=? AND route=? AND key_hash=?',(scope_hash,request.path,key)).fetchone()
    if r:
        if r['canonical_payload_hash'] is None:
            raise ApiError('IDEMPOTENCY_IN_PROGRESS',409,details={'retryAfterSeconds':2},retryable=True)
        if not secrets.compare_digest(r['canonical_payload_hash'],payload_hash):
            raise ApiError('IDEMPOTENCY_CONFLICT',409)
        if not r['encrypted_response']:
            raise ApiError('IDEMPOTENCY_CONFLICT',409,message='This action was already recorded. Reload its details.')
        response = jsonify(data=decrypt(r['encrypted_response']))
        response.status_code = 200 if r['status']==201 else r['status']
        response.headers['Idempotency-Replayed']='true'
        return response
    return None

def remember(c,scope,payload,result,status=200,entity=None,tombstone=False):
    c.execute('INSERT INTO idempotency VALUES(?,?,?,?,?,?,?,?,?,?)',(digest('actor',scope),request.path,key_required(),sha(dumps(payload)),encrypt(result),status,entity,now(),now()+7*DAY,int(tombstone)))
    return ok(result,status)

def paginate(items):
    try:
        limit=int(request.args.get('limit','25'))
        if not 1<=limit<=100: raise ValueError()
        cursor=request.args.get('cursor')
        offset=0
        if cursor:
            data=current_app.extensions['cursor'].loads(cursor,max_age=86400)
            if data['path']!=request.path: raise ValueError()
            offset=data['offset']
            if type(offset) is not int or offset<0: raise ValueError()
    except Exception:
        raise ApiError('INVALID_CURSOR',400) from None
    next_cursor=current_app.extensions['cursor'].dumps({'path':request.path,'offset':offset+limit}) if len(items)>offset+limit else None
    return {'items':items[offset:offset+limit],'nextCursor':next_cursor}
