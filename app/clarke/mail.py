"""Transactional notifications and conservative Gmail delivery, adapted from Oasis."""
import base64
import html
import json
import random
import threading
from email.message import EmailMessage
from urllib.parse import urlparse
import requests
from flask import Blueprint,current_app,g,request
from .core import ApiError,DAY,now,iso,uid,token,digest,encrypt,decrypt,body,ok,row,version,audit,replay,remember,paginate,DISCLAIMER,STATUSES
from .db import connect,transaction,settings,save_settings
from .security import require_staff
from .validation import email,boolean
from .locations import locations,route_message

bp=Blueprint('mail',__name__)
SEND_MUTEX=threading.Lock()
ITEM_LABELS={'shoes':'Shoes','boots':'Boots','handbag_purse':'Handbag or purse','belt_strap':'Belt or strap','leather_garment':'Leather jacket or garment','luggage':'Luggage','baseball_glove':'Baseball glove','other_leather':'Other leather item','keys':'Keys (ask us)'}
SAFE_ERRORS={'SENDER_DISCONNECTED':'Connect the Gmail sender, then retry.','GOOGLE_REAUTH_REQUIRED':'Reconnect the Gmail sender.','GOOGLE_UNAVAILABLE':'Google is unavailable. Delivery will be retried when safe.','DELIVERY_UNCERTAIN':'Delivery may have succeeded. Review before retrying.','GOOGLE_REJECTED':'Google rejected delivery. Check the sender and recipient.','GOOGLE_RATE_LIMIT':'Google asked us to wait before sending.','BODY_PURGED':'The retained email body has expired.','SENDER_CHANGED':'The sender changed during delivery.'}

def allowed(destination,kind='EMAILS'):
    return not current_app.config['DEMO_MODE'] or destination in current_app.config['DEMO_ALLOWED_'+kind]

def connection(c):return c.execute("SELECT * FROM integration_secrets WHERE name='gmail'").fetchone()

def policy(c,recipient,explicit_test=False):
    if not allowed(recipient):return 'demo_recipient_blocked'
    if not explicit_test and not settings(c)['emailDeliveryEnabled']:return 'delivery_disabled'
    return None

def html_body(subject,text):
    origin=current_app.config['PUBLIC_ORIGIN']
    lines=[]
    for line in text.splitlines():
        safe=html.escape(line)
        if line.startswith(origin+'/repair-status#token='):
            safe='<a href="'+html.escape(line,quote=True)+'" rel="noreferrer">View your private repair status</a>'
        elif line.startswith(origin+'/admin/'):
            safe='<a href="'+html.escape(line,quote=True)+'" rel="noreferrer">Open the staff workspace</a>'
        lines.append(safe)
    return '<html><body><h1>Clarke\'s Express Shoe Repair</h1><h2>'+html.escape(subject)+'</h2><p>'+'<br>'.join(lines)+'</p></body></html>'


def enqueue(c,event,kind,recipient,subject,text,request_id=None,offer_id=None,invite_id=None,explicit_test=False):
    ident=uid();stamp=now();reason=policy(c,recipient,explicit_test)
    payload=dict(bodyText=text,bodyHtml=html_body(subject,text))
    state='preview_only' if reason else 'pending'
    c.execute('INSERT INTO outbox(id,event_key,event_id,request_id,offer_id,invite_id,kind,recipient_norm,subject,body_cipher,policy_reason,status,sender_generation,created_at,updated_at,next_attempt_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,event+':'+kind+':'+digest('recipient',recipient),event,request_id,offer_id,invite_id,kind,recipient,subject,encrypt(payload),reason,state,connection(c)['sender_generation'],stamp,stamp,stamp if state=='pending' else None))
    return dict(id=ident,status=state)

def notify(c,r,event,kind,offer=None):
    from .repairs import reference_value,status_url
    subject={'customer_received':"We've received your Clarke's repair request",'customer_estimate':"Your Clarke's repair estimate",'customer_needs_visit':"Please bring your item to Clarke's",'customer_not_repairable':"An update on your Clarke's repair",'customer_ready':"Your Clarke's repair is ready for pickup",'staff_new_request':"New Clarke's repair request",'staff_customer_response':"A customer answered their Clarke's repair offer"}[kind]
    recipients=settings(c)['notificationEmails'] if kind.startswith('staff_') else ([r['email_norm']] if r['email_norm'] else [])
    lines=[subject+'.',reference_value(r),ITEM_LABELS[r['item_type']]]
    if kind.startswith('staff_'):
        lines += [r['description'],'Preferred contact: '+r['preferred'],current_app.config['PUBLIC_ORIGIN']+'/admin/requests/'+r['id']]
        if r['callback_phone']:lines.append('Requested callback: '+r['callback_phone'])
    else:
        if kind=='customer_received':lines.append("We'll look at your photos and reply with an estimate or ask to see it in person.")
        if r['customer_message']:lines.append(r['customer_message'])
        if offer:
            if offer['kind']=='estimate':
                amount=f"${offer['amount_min']/100:.2f}"+(f"–${offer['amount_max']/100:.2f}" if offer['amount_max'] is not None else '')
                lines += [amount,DISCLAIMER]
            lines += [offer['scope']]+([offer['timing_note']] if offer['timing_note'] else [])
        location=r['pickup_location'] if kind=='customer_ready' else r['dropoff_location']
        lines.append(route_message(location,pickup=kind=='customer_ready'))
        if kind=='customer_ready':
            card=next(x for x in locations(c)['locations'] if x['id']==location)
            lines.append(card['stateText'])
            if card['activeNotice']:lines.append(card['activeNotice']['message'])
        lines += ['This request does not confirm an appointment.',status_url(r)]
    lines += ['Bel Air: 410-836-8316. Dundalk by appointment: call or text 443-386-3800. All repairs are performed in Bel Air.']
    if not recipients and not kind.startswith('staff_'):
        audit(c,'email.skipped_no_address','request',r['id'])
    return [enqueue(c,event,kind,destination,subject,'\n\n'.join(lines),r['id'],offer['id'] if offer else None)['id'] for destination in sorted(set(recipients))]

def cancel_stale(c,r):
    for queued in c.execute("SELECT * FROM outbox WHERE request_id=? AND status IN ('pending','retry_wait') AND (offer_id IS NOT NULL OR kind='customer_ready')",(r['id'],)).fetchall():
        if not current_event(c,queued):
            c.execute("UPDATE outbox SET status='cancelled',version=version+1,updated_at=?,next_attempt_at=NULL WHERE id=?",(now(),queued['id']))

def current_event(c,r):
    if r['request_id']:
        repair=row(c,'requests',r['request_id'])
        if r['offer_id']:
            offer=row(c,'offers',r['offer_id'])
            if repair['current_offer_id']!=r['offer_id'] or offer['state']!='active' or repair['status'] not in ('estimate_sent','needs_visit'):return False
        if r['kind']=='customer_ready':
            # Only entering ready or changing its pickup location creates a new
            # ready notification. Notes/message/dropoff edits preserve that event.
            latest=c.execute("SELECT e.id FROM request_events e JOIN outbox o ON o.event_id=e.id WHERE e.request_id=? AND o.kind='customer_ready' ORDER BY e.request_version DESC,e.id DESC LIMIT 1",(r['request_id'],)).fetchone()
            if repair['status']!='ready' or not latest or latest['id']!=r['event_id']:return False
    if r['invite_id']:
        invitation=row(c,'invitations',r['invite_id'])
        if invitation['accepted_at'] or invitation['revoked_at'] or invitation['expires_at']<=now():return False
    return True

def queue_summary(c):
    counts={r['status']:r['n'] for r in c.execute('SELECT status,count(*) n FROM outbox GROUP BY status')}
    return {'pending':counts.get('pending',0)+counts.get('sending',0),'retryWait':counts.get('retry_wait',0),'failed':counts.get('failed',0),'uncertain':counts.get('uncertain',0),'previewOnly':counts.get('preview_only',0)}

def error_view(code):return dict(code=code,message=SAFE_ERRORS.get(code,'Delivery needs review.')) if code else None

def outbox_view(c,r,detail=False):
    sender=connection(c)
    can_retry=r['status'] in ('failed','uncertain','retry_wait') and bool(r['body_cipher']) and sender['state']=='connected' and policy(c,r['recipient_norm'],r['kind']=='connection_test') is None and current_event(c,r)
    data=dict(id=r['id'],requestId=r['request_id'],kind=r['kind'],recipient=r['recipient_norm'],subject=r['subject'],status=r['status'],version=r['version'],attemptCount=r['attempt_count'],createdAt=iso(r['created_at']),nextAttemptAt=iso(r['next_attempt_at']),sentAt=iso(r['sent_at']),lastError=error_view(r['last_error_code']),canRetry=can_retry,retryNeedsDuplicateAcknowledgement=r['status']=='uncertain')
    if detail:
        content=decrypt(r['body_cipher']) if r['body_cipher'] else dict(bodyText=None,bodyHtml=None)
        attempts=[dict(number=a['attempt_number'],startedAt=iso(a['started_at']),finishedAt=iso(a['finished_at']),result=a['result'],errorCode=a['error_code'],providerMessageId=a['provider_message_id']) for a in c.execute('SELECT * FROM outbox_attempts WHERE outbox_id=? ORDER BY attempt_number',(r['id'],))]
        data.update(content,policyReason=r['policy_reason'],attempts=attempts,lastRetriedBy=r['last_retried_by'],bodyPurged=not bool(r['body_cipher']))
    return data

@bp.get('/api/v1/admin/email/connection')
def get_connection():
    with connect() as c:
        r=connection(c);sender=decrypt(r['ciphertext']) if r['ciphertext'] else {}
        return ok(dict(version=r['version'],state=r['state'],senderEmail=sender.get('email'),connectedAt=iso(r['connected_at']),deliveryEnabled=settings(c)['emailDeliveryEnabled'],demoMode=current_app.config['DEMO_MODE'],lastSuccessAt=iso(r['last_success_at']),lastError=error_view(r['last_error_code']),requiresReconnect=r['state']=='reconnect_required',queue=queue_summary(c)))

@bp.post('/api/v1/admin/email/connect')
def connect_sender():
    from .auth import start
    return start(body({'expectedVersion','returnTo'}),'gmail')

def revoke_later(c,tokens):
    old=tokens.get('refresh_token') or tokens.get('access_token')
    if old:c.execute('INSERT INTO revocations VALUES(?,?,?,?,0,NULL)',(uid(),encrypt(old),now(),now()+DAY))

def replace_sender(state,tokens,identity):
    from .auth import GMAIL_SCOPE
    if GMAIL_SCOPE not in tokens.get('scope','').split():raise ApiError('SENDER_PERMISSION_DENIED',403)
    if not SEND_MUTEX.acquire(timeout=25):raise ApiError('INTEGRATION_UNAVAILABLE',503)
    try:
        with transaction() as c:
            require_staff(True,c)
            old=connection(c)
            if g.member['id']!=state['member_id'] or g.member['version']!=state['member_version'] or old['version']!=state['connection_version']:raise ApiError('VERSION_CONFLICT',409)
            previous=decrypt(old['ciphertext']) if old['ciphertext'] else {}
            if not tokens.get('refresh_token') and previous.get('sub')==identity['sub']:tokens['refresh_token']=previous.get('refresh_token')
            if not tokens.get('refresh_token'):raise ApiError('SENDER_PERMISSION_DENIED',403)
            stored={k:tokens[k] for k in ('refresh_token','access_token')}
            stored.update(email=email(identity['email']),sub=identity['sub'],expires_at=now()+int(tokens.get('expires_in',3600))*1000)
            if previous and previous.get('sub')!=identity['sub']:revoke_later(c,previous)
            c.execute("UPDATE integration_secrets SET ciphertext=?,version=version+1,sender_generation=sender_generation+1,state='connected',connected_at=?,last_error_code=NULL WHERE name='gmail'",(encrypt(stored),now()))
            c.execute("UPDATE outbox SET status='cancelled',version=version+1,updated_at=? WHERE status IN ('pending','retry_wait')",(now(),))
            audit(c,'email.sender_connected','integration','gmail',old['version'],old['version']+1)
    finally:SEND_MUTEX.release()

@bp.post('/api/v1/admin/email/disconnect')
def disconnect_sender():
    p=body({'expectedVersion'})
    acquired=SEND_MUTEX.acquire(timeout=25)
    try:
        with transaction() as c:
            require_staff(True,c);scope=g.member['id'];prior=replay(c,scope,p)
            if prior:return prior
            r=connection(c);version(p,r)
            if r['ciphertext']:revoke_later(c,decrypt(r['ciphertext']))
            c.execute("UPDATE integration_secrets SET ciphertext=NULL,state='disconnected',version=version+1,sender_generation=sender_generation+1,last_error_code=NULL WHERE name='gmail'")
            c.execute("UPDATE outbox SET status=CASE WHEN status='sending' THEN 'uncertain' ELSE 'cancelled' END,last_error_code=CASE WHEN status='sending' THEN 'SENDER_CHANGED' ELSE last_error_code END,version=version+1,updated_at=? WHERE status IN ('pending','retry_wait','sending')",(now(),))
            values=settings(c);values['emailDeliveryEnabled']=False
            pending=c.execute('SELECT pending_retention FROM settings WHERE id=1').fetchone()[0]
            save_settings(c,values,json.loads(pending) if pending else None)
            audit(c,'email.sender_disconnected','integration','gmail',r['version'],r['version']+1,summary='Sender disconnected; any in-flight delivery must be reviewed.' if not acquired else None)
            return remember(c,scope,p,dict(version=r['version']+1,state='disconnected',deliveryEnabled=False,providerRevocation='pending'))
    finally:
        if acquired:SEND_MUTEX.release()

@bp.post('/api/v1/admin/email/test')
def test_email():
    p=body({'recipient'});p['recipient']=email(p.get('recipient'),'recipient')
    with transaction() as c:
        require_staff(True,c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        if connection(c)['state']!='connected':raise ApiError('SENDER_DISCONNECTED',409)
        if not allowed(p['recipient']):raise ApiError('DEMO_DESTINATION_BLOCKED',403)
        out=enqueue(c,uid(),'connection_test',p['recipient'],"Clarke's email connection test",'This test was requested from the staff workspace.',explicit_test=True)
        audit(c,'email.test_queued','outbox',out['id'])
        return remember(c,scope,p,dict(outboxId=out['id'],status=out['status']),202,out['id'])

@bp.get('/api/v1/admin/outbox')
def get_outbox():
    clauses=[];args=[]
    for name,column in [('status','status'),('requestId','request_id')]:
        if request.args.get(name):clauses.append(column+'=?');args.append(request.args[name])
    with connect() as c:return ok(paginate(c,'outbox',lambda r:outbox_view(c,r),' AND '.join(clauses) or '1',args,filters=dict(zip(clauses,args))))

@bp.get('/api/v1/admin/outbox/<ident>')
def get_email(ident):
    with connect() as c:return ok(outbox_view(c,row(c,'outbox',ident),True))

@bp.post('/api/v1/admin/outbox/<ident>/retry')
def retry_email(ident):
    p=body({'expectedVersion','acknowledgePossibleDuplicate'})
    ack=boolean(p.get('acknowledgePossibleDuplicate',False),'acknowledgePossibleDuplicate')
    with transaction() as c:
        require_staff(True,c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        r=row(c,'outbox',ident);version(p,r)
        if not outbox_view(c,r)['canRetry']:raise ApiError('SENDER_DISCONNECTED' if connection(c)['state']!='connected' else 'EMAIL_NOT_RETRYABLE',409)
        if r['status']=='uncertain' and not ack:raise ApiError('EMAIL_NOT_RETRYABLE',409,message='Acknowledge possible duplicate delivery before retrying.')
        c.execute("UPDATE outbox SET status='pending',version=version+1,next_attempt_at=?,updated_at=?,last_retried_by=?,duplicate_ack=?,sender_generation=?,lease_token=NULL WHERE id=?",(now(),now(),g.member['id'],int(ack),connection(c)['sender_generation'],ident))
        audit(c,'email.retry_duplicate_acknowledged' if ack else 'email.retry','outbox',ident,r['version'],r['version']+1)
        return remember(c,scope,p,dict(id=ident,status='pending',version=r['version']+1,attemptCount=r['attempt_count'],nextAttemptAt=iso(now())),202,ident)

class DeliveryFailure(Exception):
    def __init__(self,status,code,delay=0):self.status,self.code,self.delay=status,code,delay

def refresh_sender(sender,generation):
    try:
        response=requests.post('https://oauth2.googleapis.com/token',data=dict(client_id=current_app.config['GOOGLE_CLIENT_ID'],client_secret=current_app.config['GOOGLE_CLIENT_SECRET'],refresh_token=sender['refresh_token'],grant_type='refresh_token'),timeout=(5,15))
        if response.status_code==400 and response.json().get('error')=='invalid_grant':raise DeliveryFailure('failed','GOOGLE_REAUTH_REQUIRED')
        if response.status_code==429 or response.status_code>=500:raise DeliveryFailure('retry_wait','GOOGLE_UNAVAILABLE')
        if not response.ok:raise DeliveryFailure('failed','GOOGLE_REAUTH_REQUIRED')
        fresh=response.json();sender.update(access_token=fresh['access_token'],expires_at=now()+int(fresh.get('expires_in',3600))*1000)
        with transaction() as c:c.execute("UPDATE integration_secrets SET ciphertext=?,state='connected',last_error_code=NULL WHERE name='gmail' AND sender_generation=?",(encrypt(sender),generation))
        return sender
    except requests.RequestException:raise DeliveryFailure('retry_wait','GOOGLE_UNAVAILABLE') from None
    except (KeyError,ValueError):raise DeliveryFailure('failed','GOOGLE_REAUTH_REQUIRED') from None

def deliver(r,sender):
    if sender.get('expires_at',0)<now()+90000:sender=refresh_sender(sender,r['sender_generation'])
    content=decrypt(r['body_cipher']);message=EmailMessage()
    message['From']="Clarke's Express Shoe Repair <"+sender['email']+'>';message['To']=r['recipient_norm'];message['Subject']=r['subject']
    message['Message-ID']='<clarke-'+r['id']+'@'+urlparse(current_app.config['PUBLIC_ORIGIN']).hostname+'>'
    message.set_content(content['bodyText']);message.add_alternative(content['bodyHtml'],subtype='html')
    for attempt in range(2):
        try:
            response=requests.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',headers={'Authorization':'Bearer '+sender['access_token']},json={'raw':base64.urlsafe_b64encode(message.as_bytes()).decode()},timeout=(5,15))
        except requests.ConnectTimeout:raise DeliveryFailure('retry_wait','GOOGLE_UNAVAILABLE') from None
        except requests.RequestException:raise DeliveryFailure('uncertain','DELIVERY_UNCERTAIN') from None
        if response.status_code==401 and attempt==0:
            sender=refresh_sender(sender,r['sender_generation']);continue
        if response.status_code==401:raise DeliveryFailure('failed','GOOGLE_REAUTH_REQUIRED')
        if response.status_code==429:
            try:delay=max(0,min(86400,int(response.headers.get('Retry-After','0'))))*1000
            except ValueError:delay=0
            raise DeliveryFailure('retry_wait','GOOGLE_RATE_LIMIT',delay)
        if response.status_code>=500:raise DeliveryFailure('uncertain','DELIVERY_UNCERTAIN')
        if not response.ok:raise DeliveryFailure('failed','GOOGLE_REJECTED')
        try:
            ident=response.json()['id']
            if not isinstance(ident,str) or len(ident)>128:raise ValueError()
            return ident
        except (ValueError,KeyError):raise DeliveryFailure('uncertain','DELIVERY_UNCERTAIN') from None

def drain_one():
    if not SEND_MUTEX.acquire(blocking=False):return
    try:
        with transaction() as c:
            c.execute("UPDATE outbox_attempts SET result='uncertain',finished_at=?,error_code='DELIVERY_UNCERTAIN' WHERE finished_at IS NULL AND outbox_id IN (SELECT id FROM outbox WHERE status='sending' AND lease_expires_at<=?)",(now(),now()))
            c.execute("UPDATE outbox SET status='uncertain',last_error_code='DELIVERY_UNCERTAIN',version=version+1,updated_at=? WHERE status='sending' AND lease_expires_at<=?",(now(),now()))
            r=c.execute("SELECT * FROM outbox WHERE status IN ('pending','retry_wait') AND next_attempt_at<=? ORDER BY created_at,id LIMIT 1",(now(),)).fetchone()
            if not r:return
            r=dict(r);conn=connection(c)
            if not current_event(c,r):
                c.execute("UPDATE outbox SET status='cancelled',version=version+1,updated_at=? WHERE id=?",(now(),r['id']));return
            reason=policy(c,r['recipient_norm'],r['kind']=='connection_test')
            if reason:
                c.execute("UPDATE outbox SET status='preview_only',policy_reason=?,version=version+1,updated_at=? WHERE id=?",(reason,now(),r['id']));return
            if conn['state'] not in ('connected','degraded') or not conn['ciphertext']:
                c.execute("UPDATE outbox SET status='failed',last_error_code='SENDER_DISCONNECTED',version=version+1,updated_at=? WHERE id=?",(now(),r['id']));return
            if conn['sender_generation']!=r['sender_generation']:
                c.execute("UPDATE outbox SET status='cancelled',version=version+1,updated_at=? WHERE id=?",(now(),r['id']));return
            lease=token();number=r['attempt_count']+1;r['attempt_count']=number
            c.execute("UPDATE outbox SET status='sending',attempt_count=?,lease_token=?,lease_expires_at=?,updated_at=?,version=version+1 WHERE id=?",(number,lease,now()+120000,now(),r['id']))
            c.execute('INSERT INTO outbox_attempts VALUES(?,?,?,?,NULL,?,NULL,NULL,?,?)',(uid(),r['id'],number,now(),'sending',r['last_retried_by'],r['duplicate_ack']))
            sender=decrypt(conn['ciphertext'])
        state,code,provider,delay='sent',None,None,0
        try:provider=deliver(r,sender)
        except DeliveryFailure as error:state,code,delay=error.status,error.code,error.delay
        except Exception:state,code='uncertain','DELIVERY_UNCERTAIN'
        with transaction() as c:
            latest=row(c,'outbox',r['id']);generation=connection(c)['sender_generation']
            if latest['lease_token']!=lease:return
            if generation!=r['sender_generation'] or latest['status']!='sending':state,code,provider='uncertain','SENDER_CHANGED',None
            if state=='retry_wait' and number>=6:state='failed'
            next_at=now()+max(delay,int([60000,300000,1800000,7200000,43200000][min(number-1,4)]*random.uniform(1,1.2))) if state=='retry_wait' else None
            c.execute('UPDATE outbox SET status=?,last_error_code=?,provider_message_id=?,next_attempt_at=?,sent_at=?,updated_at=?,version=version+1,lease_token=NULL,lease_expires_at=NULL WHERE id=?',(state,code,provider,next_at,now() if state=='sent' else None,now(),r['id']))
            c.execute('UPDATE outbox_attempts SET finished_at=?,result=?,error_code=?,provider_message_id=? WHERE outbox_id=? AND attempt_number=?',(now(),state,code,provider,r['id'],number))
            if code=='GOOGLE_REAUTH_REQUIRED':c.execute("UPDATE integration_secrets SET state='reconnect_required',last_error_code=? WHERE name='gmail' AND sender_generation=?",(code,generation))
            elif state=='sent':c.execute("UPDATE integration_secrets SET state='connected',last_success_at=?,last_error_code=NULL WHERE name='gmail' AND sender_generation=?",(now(),generation))
            audit(c,'email.'+state,'outbox',r['id'])
    finally:SEND_MUTEX.release()

def revoke_one():
    with connect() as c:r=c.execute('SELECT * FROM revocations WHERE encrypted_token IS NOT NULL AND due_at<=? ORDER BY due_at LIMIT 1',(now(),)).fetchone()
    if not r:return
    outcome=None
    if r['expires_at']<=now():outcome='expired'
    else:
        try:
            response=requests.post('https://oauth2.googleapis.com/revoke',data={'token':decrypt(r['encrypted_token'])},timeout=(5,10))
            if response.ok or response.status_code==400:outcome='revoked'
        except requests.RequestException:pass
    with transaction() as c:c.execute('UPDATE revocations SET encrypted_token=CASE WHEN ? IS NOT NULL THEN NULL ELSE encrypted_token END,outcome=?,attempt_count=attempt_count+1,due_at=? WHERE id=?',(outcome,outcome,now()+min(3600000,60000*2**min(r['attempt_count'],6)),r['id']))
