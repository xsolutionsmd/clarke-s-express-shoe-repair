"""Repair requests, immutable offers and minimized customer projections."""
import json
import secrets
import time
from datetime import datetime,date
from urllib.parse import quote
from flask import Blueprint,current_app,g,request
from .core import ApiError,DAY,CLOSED,LOCATIONS,STATUSES,DISCLAIMER,now,iso,uid,token,digest,encrypt,decrypt,body,ok,row,version,audit,replay,remember,paginate,fail
from .db import connect,transaction,settings
from .security import require_staff,limit,trusted_ip
from .validation import repair,needed_by_current,text,enum,phone,reference,unique_array,integer,NY,email
from .locations import locations,route_message

bp=Blueprint('repairs',__name__)
REPAIR_FIELDS={'itemType','workTypes','description','brandAge','location','neededBy','contact'}

def reference_value(r):return decrypt(r['reference_cipher'])
def status_url(r):return current_app.config['PUBLIC_ORIGIN']+'/repair-status#token='+decrypt(r['status_token_cipher'])

def status_valid(c,r):return bool(r and (r['closed_at'] is None or now()<r['closed_at']+settings(c)['closedLinkDays']*DAY))

def bearer(c):
    authorization=request.headers.get('Authorization','')
    raw=authorization[7:] if authorization.startswith('Bearer ') else ''
    r=c.execute('SELECT * FROM requests WHERE status_token_hash=?',(digest('status',raw),)).fetchone()
    if not status_valid(c,r):raise ApiError('STATUS_UNAVAILABLE',404)
    return r

def event(c,r,kind,message=None,old=None,reason=None,visibility='customer',offer=None):
    ident=uid()
    c.execute('INSERT INTO request_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ident,r['id'],kind,old,r['status'],message,visibility,g.member['id'] if getattr(g,'member',None) else None,reason,offer,r['version'],now()))
    return ident

def event_view(r,private=False):
    result=dict(id=r['id'],type=r['type'],status=r['status'],message=r['public_message'],at=iso(r['created_at']))
    if private:result.update(fromStatus=r['from_status'],visibility=r['visibility'],actorId=r['actor_id'],reason=r['reason'])
    return result

def offer_view(c,r,private=False):
    if not r:return None
    response=c.execute('SELECT * FROM customer_responses WHERE offer_id=?',(r['id'],)).fetchone()
    result=dict(id=r['id'],kind=r['kind'],currency='USD',amountMinCents=r['amount_min'],amountMaxCents=r['amount_max'],scope=r['scope'],timingNote=r['timing_note'],disclaimer=DISCLAIMER if r['kind']=='estimate' else None,sentAt=iso(r['created_at']),response=dict(id=response['id'],choice=response['choice'],recordedAt=iso(response['created_at'])) if response else None)
    if private:result.update(version=r['version'],state=r['state'],createdBy=r['created_by'],customerMessage=r['customer_message'])
    return result

def current_offer(c,r):return c.execute('SELECT * FROM offers WHERE id=? AND request_id=?',(r['current_offer_id'],r['id'])).fetchone() if r['current_offer_id'] else None

def delivery(c,ident):
    values={r['status']:r['n'] for r in c.execute('SELECT status,count(*) n FROM outbox WHERE request_id=? GROUP BY status',(ident,))}
    return dict(failed=values.get('failed',0),uncertain=values.get('uncertain',0),pending=sum(values.get(k,0) for k in ('pending','sending','retry_wait')),previewOnly=values.get('preview_only',0))

def public_status(c,r):
    offer=current_offer(c,r)
    active=offer and offer['state']=='active' and r['status'] in ('estimate_sent','needs_visit')
    history=list(c.execute("SELECT * FROM request_events WHERE request_id=? AND visibility='customer' ORDER BY created_at DESC,id DESC LIMIT 50",(r['id'],)))
    next_action={'new':"We'll review your request and reply with an estimate or ask to see it in person.",'reviewing':"We're reviewing your request.",'estimate_sent':'Review the estimate.','needs_visit':'Please bring the item in so we can examine it.','not_repairable':'Call the shop if you would like to discuss the assessment.','awaiting_dropoff':'Your response is recorded.','in_shop':'Your item is in the shop.','in_progress':'Your repair is in progress.','ready':'Your item is ready for pickup.','picked_up':'Your item has been collected.','cancelled':'This request is closed.'}[r['status']]
    next_action+=' '+route_message(r['pickup_location'] if r['status']=='ready' else r['dropoff_location'])
    return dict(reference=reference_value(r),version=r['version'],status=r['status'],statusLabel=STATUSES[r['status']],itemType=r['item_type'],dropoffLocation=r['dropoff_location'],pickupLocation=r['pickup_location'],appointmentConfirmed=False,updatedAt=iso(r['updated_at']),nextAction=next_action,customerMessage=r['customer_message'],offer=offer_view(c,offer) if offer and offer['state']!='superseded' else None,allowedResponses=['accept','decline','request_call'] if active else [],history=[event_view(x) for x in reversed(history)],locationDataUrl='/api/v1/locations')

def summary(c,r):
    offer=current_offer(c,r)
    return dict(id=r['id'],reference=reference_value(r),source=r['source'],status=r['status'],version=r['version'],itemType=r['item_type'],customerName=r['contact_name'],dropoffLocation=r['dropoff_location'],neededBy=r['needed_by'],createdAt=iso(r['created_at']),updatedAt=iso(r['updated_at']),photoCount=c.execute("SELECT count(*) FROM photos WHERE request_id=? AND state<>'deleted'",(r['id'],)).fetchone()[0],delivery=delivery(c,r['id']),responsePending=bool(offer and offer['state']=='active'))

def detail(c,r):
    from .uploads import photo_view
    photos=[]
    for p in c.execute("SELECT * FROM photos WHERE request_id=? AND state<>'deleted' ORDER BY slot",(r['id'],)):
        photos.append(photo_view(p)|{'url':'/api/v1/admin/requests/'+r['id']+'/photos/'+p['id']})
    return dict(id=r['id'],reference=reference_value(r),source=r['source'],status=r['status'],version=r['version'],itemType=r['item_type'],workTypes=json.loads(r['work_types']),description=r['description'],brandAge=r['brand_age'],neededBy=r['needed_by'],contact=dict(name=r['contact_name'],email=r['email_norm'],phone=r['phone_e164'],preferred=r['preferred'],callbackPhone=r['callback_phone']),dropoffLocation=r['dropoff_location'],pickupLocation=r['pickup_location'],repairLocation='bel_air',customerMessage=r['customer_message'],offer=offer_view(c,current_offer(c,r),True),photos=photos,createdAt=iso(r['created_at']),updatedAt=iso(r['updated_at']),closedAt=iso(r['closed_at']),delivery=delivery(c,r['id']),demoMode=current_app.config['DEMO_MODE'],links={key:'/api/v1/admin/requests/'+r['id']+'/'+key for key in ('events','notes','offers')})

def create_record(c,p,source):
    ident=uid();symbols=''.join(secrets.choice('0123456789ABCDEFGHJKMNPQRSTVWXYZ') for _ in range(26))
    ref='CLK-'+'-'.join([symbols[:5],symbols[5:10],symbols[10:15],symbols[15:20],symbols[20:]])
    raw=token();stamp=now();contact=p['contact']
    c.execute('INSERT INTO requests(id,reference_hash,reference_cipher,status_token_hash,status_token_cipher,source,data_mode,status,item_type,work_types,description,brand_age,needed_by,contact_name,email_norm,phone_e164,preferred,dropoff_location,pickup_location,created_at,updated_at,consent_version,accepted_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,digest('reference',symbols),encrypt(ref),digest('status',raw),encrypt(raw),source,'demo' if current_app.config['DEMO_MODE'] else 'operational','new' if source=='online' else 'in_shop',p['itemType'],json.dumps(p['workTypes']),p['description'],p['brandAge'],p['neededBy'],contact['name'],contact['email'],contact['phone'],contact['preferred'],p['location'],p['location'],stamp,stamp,'repair-intake-v1' if source=='online' else None,stamp if source=='online' else None))
    return row(c,'requests',ident)

def receipt(c,r):
    card=locations(c)['locations'][0]
    warning=[]
    if r['needed_by'] and (date.fromisoformat(r['needed_by'])-datetime.fromtimestamp(now()/1000,NY).date()).days<=3:warning=[dict(code='TIMING_NOT_CONFIRMED',message='Timing is confirmed only after we review your request.')]
    closure=None
    if card['state'] not in ('open','closing_soon'):
        closure="We're closed right now; we'll review your request when we reopen."
        if card['nextOpensAt']:closure+=' '+card['stateText']+'.'
        if card['activeNotice']:closure+=' '+card['activeNotice']['message']
    return dict(reference=reference_value(r),status=r['status'],createdAt=iso(r['created_at']),statusUrl=status_url(r),location=r['dropoff_location'],appointmentConfirmed=False,message="We've received your repair request. We'll look at your photos and reply with an estimate or ask to see it in person.",locationMessage=('This is a request for contact, not an appointment. ' if r['dropoff_location']=='dundalk' else '')+route_message(r['dropoff_location']),closureMessage=closure,nextOpensAt=card['nextOpensAt'],warnings=warning,notifications={'recorded':True})

@bp.post('/api/v1/requests')
def submit():
    from .uploads import authorize_draft
    from .mail import notify
    original=body(REPAIR_FIELDS|{'draftId','photoIds','consentVersion','website'})
    p=repair(original,validate_time=False);p.update(draftId=text(original.get('draftId'),'draftId',1,100),photoIds=unique_array(original.get('photoIds',[]),'photoIds',None,5),consentVersion=enum(original.get('consentVersion'),{'repair-intake-v1'},'consentVersion'),website=original.get('website',''))
    if p['website']!='':raise ApiError('VALIDATION_FAILED')
    with transaction() as c:
        draft=authorize_draft(c,p['draftId']);scope='draft:'+draft['id'];prior=replay(c,scope,p)
        if prior:return prior
        if draft['state']=='submitted':return remember(c,scope,p,decrypt(draft['receipt_cipher']),200,draft['request_id'],True)
        needed_by_current(p['neededBy'])
        if not settings(c)['intakeAccepting']:raise ApiError('INTAKE_PAUSED',409,details={'message':settings(c)['intakePauseMessage']})
        limit(c,'request-ip',trusted_ip(),10,3600000)
        for field in ('email','phone'):
            if p['contact'][field]:limit(c,'request-'+field,p['contact'][field],3,3600000)
        photos=list(c.execute("SELECT * FROM photos WHERE draft_id=? AND state<>'deleted'",(draft['id'],)))
        if {x['id'] for x in photos}!=set(p['photoIds']) or any(x['state']!='ready' or x['request_id'] for x in photos):raise ApiError('PHOTOS_NOT_READY',409)
        r=create_record(c,p,'online');ev=event(c,r,'received','Request received.')
        c.execute("UPDATE photos SET request_id=?,attached_at=? WHERE draft_id=? AND state='ready'",(r['id'],now(),draft['id']))
        result=receipt(c,r)
        c.execute("UPDATE drafts SET state='submitted',request_id=?,receipt_cipher=? WHERE id=?",(r['id'],encrypt(result),draft['id']))
        notify(c,r,ev,'customer_received');notify(c,r,ev,'staff_new_request');audit(c,'request.created','request',r['id'],None,1)
        return remember(c,scope,p,result,201,r['id'],True)

@bp.post('/api/v1/status/lookup')
def lookup():
    started=time.monotonic();p=body({'reference','verification'})
    ref=reference(p.get('reference'));verification=p.get('verification')
    with transaction() as c:
        limit(c,'lookup-ip',trusted_ip(),10,900000);limit(c,'lookup-reference',ref or 'invalid',5,900000)
    try:
        with connect() as c:
            r=c.execute('SELECT * FROM requests WHERE reference_hash=?',(digest('reference',ref),)).fetchone()
            match=False
            if isinstance(verification,dict) and set(verification)=={'type','value'} and isinstance(verification['value'],str):
                if verification['type']=='email':
                    candidate=verification['value'].strip().casefold();stored=r['email_norm'] if r else ''
                    match=secrets.compare_digest(digest('verification',candidate),digest('verification',stored or '')) and bool(stored)
                elif verification['type']=='phone_last4':
                    value=verification['value'];stored=r['phone_e164'] if r else None
                    match=len(value)==4 and value.isascii() and value.isdigit() and secrets.compare_digest(digest('verification',value),digest('verification',(stored or '')[-4:])) and bool(stored)
            if not match or not status_valid(c,r):raise ApiError('STATUS_UNAVAILABLE',404)
            return ok(dict(statusToken=decrypt(r['status_token_cipher']),statusUrl=status_url(r)))
    finally:time.sleep(max(0,0.12-(time.monotonic()-started)))

@bp.get('/api/v1/status')
def get_status():
    with transaction() as c:
        r=bearer(c);limit(c,'status-ip',trusted_ip(),60,60000);limit(c,'status-token',r['id'],30,60000)
        return ok(public_status(c,r))

@bp.get('/api/v1/status/events')
def get_public_events():
    with transaction() as c:
        r=bearer(c)
        limit(c,'status-ip',trusted_ip(),60,60000);limit(c,'status-token',r['id'],30,60000)
        return ok(paginate(c,'request_events',event_view,"request_id=? AND visibility='customer'",(r['id'],),scope='status:'+r['id']+':'+r['status_token_hash']))

@bp.post('/api/v1/status/responses')
def respond():
    from .mail import notify,cancel_stale
    p=body({'offerId','expectedVersion','choice','phone'})
    p['choice']=enum(p.get('choice'),{'accept','decline','request_call'},'choice')
    if p['choice']=='request_call':p['phone']=phone(p.get('phone'))
    elif p.get('phone') is not None:fail('phone','A phone number is only accepted for a callback request.')
    with transaction() as c:
        r=bearer(c);scope='status:'+r['id'];prior=replay(c,scope,p)
        if prior:return prior
        offer=c.execute('SELECT * FROM offers WHERE id=? AND request_id=?',(p.get('offerId'),r['id'])).fetchone()
        if not offer or offer['state']=='superseded' or offer['id']!=r['current_offer_id']:raise ApiError('OFFER_SUPERSEDED',409)
        if offer['state']=='answered':raise ApiError('RESPONSE_ALREADY_RECORDED',409)
        version(p,r)
        if r['status'] not in ('estimate_sent','needs_visit'):raise ApiError('INVALID_TRANSITION',409)
        limit(c,'response-ip',trusted_ip(),10,900000);limit(c,'response-offer',offer['id'],5,900000)
        ident=uid();stamp=now();state={'accept':'awaiting_dropoff','decline':'cancelled','request_call':r['status']}[p['choice']]
        c.execute('INSERT INTO customer_responses VALUES(?,?,?,?,?,?)',(ident,r['id'],offer['id'],p['choice'],p.get('phone'),stamp))
        c.execute("UPDATE offers SET state='answered',version=version+1 WHERE id=?",(offer['id'],))
        c.execute('UPDATE requests SET status=?,closed_at=?,callback_phone=COALESCE(?,callback_phone),updated_at=?,version=version+1 WHERE id=? AND version=?',(state,stamp if state in CLOSED else None,p.get('phone'),stamp,r['id'],r['version']))
        newer=row(c,'requests',r['id']);ev=event(c,newer,'customer_response','Response recorded.',r['status'],offer=offer['id'])
        cancel_stale(c,newer);notify(c,newer,ev,'staff_customer_response');audit(c,'request.customer_response','request',r['id'],r['version'],newer['version'])
        return remember(c,scope,p,dict(responseId=ident,offerId=offer['id'],choice=p['choice'],status=state,version=newer['version'],recordedAt=iso(stamp),message='Response recorded. '+route_message(r['dropoff_location'])),200,r['id'])

@bp.get('/api/v1/admin/requests')
def inbox():
    filters={'new':['new','reviewing'],'waiting':['estimate_sent','needs_visit','awaiting_dropoff'],'in_shop':['in_shop','in_progress'],'ready':['ready'],'closed':['picked_up','cancelled'],'all':list(STATUSES)}
    selected=enum(request.args.get('filter','new'),set(filters),'filter');states=filters[selected]
    if request.args.get('status'):
        if selected!='all':fail('status')
        states=[enum(request.args['status'],set(STATUSES),'status')]
    where=['status IN ('+','.join('?' for _ in states)+')'];args=list(states)
    if request.args.get('location'):where.append('dropoff_location=?');args.append(enum(request.args['location'],LOCATIONS,'location'))
    query=request.args.get('q','').strip()
    if query:
        text(query,'q',2,100);ref=reference(query)
        if ref:where.append('reference_hash=?');args.append(digest('reference',ref))
        else:
            escaped=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_').casefold()
            where.append("(lower(contact_name) LIKE ? ESCAPE '\\' OR email_norm LIKE ? ESCAPE '\\' OR phone_e164 LIKE ? ESCAPE '\\')")
            normalized=''.join(ch for ch in query if ch.isdigit()) if any(ch.isdigit() for ch in query) else escaped
            args.extend(['%'+escaped+'%','%'+escaped+'%','%'+normalized+'%'])
    with connect() as c:
        return ok(paginate(c,'requests',lambda r:summary(c,r),' AND '.join(where),args,order=("(status='new')",'created_at','id'),filters={'where':where,'args':args}))

@bp.get('/api/v1/admin/requests/<ident>')
def get_detail(ident):
    with connect() as c:return ok(detail(c,row(c,'requests',ident)))

@bp.post('/api/v1/admin/requests')
def walk_in():
    from .mail import notify
    original=body(REPAIR_FIELDS|{'internalNote'});p=repair(original,False,validate_time=False);p['internalNote']=text(original.get('internalNote'),'internalNote',1,4000,True)
    with transaction() as c:
        require_staff(c=c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        needed_by_current(p['neededBy'])
        r=create_record(c,p,'walk_in');ev=event(c,r,'received','Item received in the shop.')
        if p['internalNote']:c.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)',(uid(),r['id'],g.member['id'],p['internalNote'],now(),1))
        notify(c,r,ev,'customer_received');notify(c,r,ev,'staff_new_request');audit(c,'request.walk_in','request',r['id'],None,1)
        result=dict(id=r['id'],reference=reference_value(r),status=r['status'],version=1,source='walk_in',createdAt=iso(r['created_at']),statusUrl=status_url(r))
        return remember(c,scope,p,result,201,r['id'],True)

def validate_transition(source,target,reason=None,offer=False):
    order=['new','reviewing','estimate_sent','needs_visit','awaiting_dropoff','in_shop','in_progress','ready','picked_up']
    backward=(source in CLOSED and target not in CLOSED) or (source=='not_repairable' and target!='cancelled') or (target in order and source in order and order.index(target)<order.index(source))
    if offer and (source in CLOSED or (target!=source and backward)):
        raise ApiError('INVALID_TRANSITION',409,message='First move this request back to reviewing with a staff reason, then publish an offer.')
    if target!=source and backward and not reason:
        fail('reason','Explain this backward change in at least ten characters.')


@bp.patch('/api/v1/admin/requests/<ident>')
def update_request(ident):
    from .mail import notify,cancel_stale
    p=body({'expectedVersion','status','pickupLocation','dropoffLocation','customerMessage','reason'})
    with transaction() as c:
        require_staff(c=c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        r=row(c,'requests',ident);version(p,r);target=enum(p.get('status',r['status']),set(STATUSES),'status')
        if target in ('estimate_sent','needs_visit') and target!=r['status']:raise ApiError('INVALID_TRANSITION',409,message='Publish a new offer to request a customer response.')
        pickup=enum(p.get('pickupLocation',r['pickup_location']),LOCATIONS,'pickupLocation');dropoff=enum(p.get('dropoffLocation',r['dropoff_location']),LOCATIONS,'dropoffLocation')
        if target=='ready' and 'pickupLocation' not in p and r['status']!='ready':fail('pickupLocation','Choose the pickup location.')
        message=text(p.get('customerMessage',r['customer_message']),'customerMessage',1,2000,True)
        if target=='not_repairable' and not message:fail('customerMessage','Explain the assessment for the customer.')
        reason=text(p.get('reason'),'reason',10,500,True)
        validate_transition(r['status'],target,reason)
        changed=(target,pickup,dropoff,message)!=(r['status'],r['pickup_location'],r['dropoff_location'],r['customer_message'])
        if not changed:return remember(c,scope,p,dict(id=ident,status=target,version=r['version'],updatedAt=iso(r['updated_at']),notificationEventIds=[]))
        closed=now() if target in CLOSED and r['closed_at'] is None else r['closed_at'] if target in CLOSED else None
        if r['closed_at'] and target not in CLOSED and not status_valid(c,r):
            raw=token();c.execute('UPDATE requests SET status_token_hash=?,status_token_cipher=? WHERE id=?',(digest('status',raw),encrypt(raw),ident));audit(c,'request.status_token_rotated','request',ident)
        offer=current_offer(c,r)
        if offer and offer['state']=='active' and target!=('estimate_sent' if offer['kind']=='estimate' else 'needs_visit'):
            c.execute("UPDATE offers SET state='superseded',version=version+1 WHERE id=?",(offer['id'],))
        c.execute('UPDATE requests SET status=?,pickup_location=?,dropoff_location=?,customer_message=?,closed_at=?,updated_at=?,version=version+1 WHERE id=? AND version=?',(target,pickup,dropoff,message,closed,now(),ident,r['version']))
        newer=row(c,'requests',ident);ev=event(c,newer,'status_changed',message or STATUSES[target]+'.',r['status'],reason)
        notifications=[]
        if target in ('ready','not_repairable') and (target!=r['status'] or (target=='ready' and pickup!=r['pickup_location'])):notifications=notify(c,newer,ev,'customer_'+target)
        cancel_stale(c,newer)
        audit(c,'request.status_changed','request',ident,r['version'],newer['version'],summary='Status changed from '+r['status']+' to '+target+'.')
        return remember(c,scope,p,dict(id=ident,status=target,version=newer['version'],updatedAt=iso(newer['updated_at']),notificationEventIds=notifications))

@bp.post('/api/v1/admin/requests/<ident>/offers')
def create_offer(ident):
    from .mail import notify,cancel_stale
    p=body({'expectedVersion','kind','amountMinCents','amountMaxCents','scope','timingNote','customerMessage'})
    p['kind']=enum(p.get('kind'),{'estimate','visit'},'kind')
    if p['kind']=='estimate':
        p['amountMinCents']=integer(p.get('amountMinCents'),'amountMinCents',1,100000000)
        p['amountMaxCents']=integer(p['amountMaxCents'],'amountMaxCents',p['amountMinCents'],100000000) if p.get('amountMaxCents') is not None else None
    elif p.get('amountMinCents') is not None or p.get('amountMaxCents') is not None:fail('amountMinCents','A visit request has no amount.')
    p['scope']=text(p.get('scope'),'scope',10,2000);p['timingNote']=text(p.get('timingNote'),'timingNote',1,300,True);p['customerMessage']=text(p.get('customerMessage'),'customerMessage',1,2000,True)
    with transaction() as c:
        require_staff(c=c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        r=row(c,'requests',ident);version(p,r)
        status='estimate_sent' if p['kind']=='estimate' else 'needs_visit'
        validate_transition(r['status'],status,offer=True)
        c.execute("UPDATE offers SET state='superseded',version=version+1 WHERE request_id=? AND state='active'",(ident,))
        offer_id=uid();stamp=now()
        c.execute("INSERT INTO offers VALUES(?,?,?,'active','USD',?,?,?,?,?,?,?,1)",(offer_id,ident,p['kind'],p.get('amountMinCents'),p.get('amountMaxCents'),p['scope'],p['timingNote'],p['customerMessage'],g.member['id'],stamp))
        c.execute('UPDATE requests SET current_offer_id=?,status=?,customer_message=?,version=version+1,updated_at=? WHERE id=? AND version=?',(offer_id,status,p['customerMessage'],stamp,ident,r['version']))
        newer=row(c,'requests',ident);ev=event(c,newer,'offer_sent',STATUSES[status]+'.',r['status'],offer=offer_id)
        cancel_stale(c,newer);notifications=notify(c,newer,ev,'customer_estimate' if p['kind']=='estimate' else 'customer_needs_visit',row(c,'offers',offer_id));audit(c,'request.offer_created','request',ident,r['version'],newer['version'])
        return remember(c,scope,p,dict(offerId=offer_id,kind=p['kind'],status=status,version=newer['version'],sentAt=iso(stamp),notificationEventIds=notifications),201,offer_id)

@bp.post('/api/v1/admin/requests/<ident>/notes')
def create_note(ident):
    p=body({'expectedVersion','text'});p['text']=text(p.get('text'),'text',1,4000)
    with transaction() as c:
        require_staff(c=c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        r=row(c,'requests',ident);version(p,r);note_id=uid();stamp=now()
        c.execute('INSERT INTO notes VALUES(?,?,?,?,?,?)',(note_id,ident,g.member['id'],p['text'],stamp,r['version']+1))
        c.execute('UPDATE requests SET version=version+1,updated_at=? WHERE id=? AND version=?',(stamp,ident,r['version']))
        event(c,row(c,'requests',ident),'internal_note',None,visibility='internal');audit(c,'request.note_added','request',ident,r['version'],r['version']+1)
        return remember(c,scope,p,dict(id=note_id,text=p['text'],authorId=g.member['id'],createdAt=iso(stamp),requestVersion=r['version']+1),201,note_id)

@bp.get('/api/v1/admin/requests/<ident>/<collection>')
def children(ident,collection):
    if collection not in ('events','notes','offers','contact-actions'):raise ApiError('NOT_FOUND',404)
    with connect() as c:
        r=row(c,'requests',ident)
        if collection=='contact-actions':
            from .mail import allowed
            ph=r['phone_e164'];em=r['email_norm'];phone_ok=ph and allowed(ph,'PHONES');email_ok=em and allowed(em)
            return ok(dict(callHref='tel:'+ph if phone_ok else None,smsHref='sms:'+ph if phone_ok else None,emailHref='mailto:'+em if email_ok else None,blockedByDemo=bool((ph and not phone_ok) or (em and not email_ok))))
        table='request_events' if collection=='events' else collection
        project=lambda x:event_view(x,True) if collection=='events' else offer_view(c,x,True) if collection=='offers' else dict(id=x['id'],text=x['text'],authorId=x['author_id'],createdAt=iso(x['created_at']))
        return ok(paginate(c,table,project,'request_id=?',(ident,)))

@bp.post('/api/v1/admin/requests/<ident>/share-link')
def share(ident):
    from .mail import allowed
    p=body({'channel'});channel=enum(p.get('channel'),{'print','text'},'channel')
    with transaction() as c:
        require_staff(c=c);r=row(c,'requests',ident)
        if not status_valid(c,r):raise ApiError('STATUS_UNAVAILABLE',404)
        if channel=='text' and not r['phone_e164']:fail('channel','This ticket has no phone number.')
        url=status_url(r);message="Your Clarke's repair status: "+url
        eligible=channel=='text' and allowed(r['phone_e164'],'PHONES')
        audit(c,'request.share_'+channel,'request',ident)
        return ok(dict(reference=reference_value(r),statusUrl=url,channel=channel,smsHref='sms:'+r['phone_e164']+'?body='+quote(message,safe='') if eligible else None,message=message,deliveryState='print' if channel=='print' else 'manual' if eligible else 'preview_only'))
