import json
from flask import Blueprint,current_app,g,request
from .core import ApiError,DAY,now,iso,uid,body,ok,row,version,audit,replay,remember,paginate,fail
from .db import connect,transaction,settings,save_settings
from .security import require_staff
from .validation import text,integer,boolean,email,unique_array,enum
from .locations import validate_hours,notice_input,notice_view

bp=Blueprint('admin',__name__)
SETTINGS_FIELDS={'intakeAccepting','intakePauseMessage','notificationEmails','emailDeliveryEnabled','responseExpectation','photoRetentionDays','closedLinkDays'}

def settings_view(c):
    r=c.execute('SELECT * FROM settings WHERE id=1').fetchone()
    return dict(version=r['version'],**json.loads(r['data']),pendingRetention=json.loads(r['pending_retention']) if r['pending_retention'] else None,demoMode=current_app.config['DEMO_MODE'],testDestinationPolicy=dict(emailAllowlistConfigured=bool(current_app.config['DEMO_ALLOWED_EMAILS']),phoneAllowlistConfigured=bool(current_app.config['DEMO_ALLOWED_PHONES'])),updatedAt=iso(r['updated_at']))

@bp.get('/api/v1/admin/settings')
def get_settings():
    with connect() as c:return ok(settings_view(c))

def retention(c,p):
    photo=integer(p.get('photoRetentionDays'),'photoRetentionDays',1,730)
    link=integer(p.get('closedLinkDays'),'closedLinkDays',1,365)
    current=settings(c)
    return dict(photosEligibleForDeletion=c.execute("SELECT count(*) FROM photos p JOIN requests r ON p.request_id=r.id WHERE p.state='ready' AND r.closed_at IS NOT NULL AND r.closed_at<=?",(now()-photo*DAY,)).fetchone()[0],linksBecomingUnavailable=c.execute('SELECT count(*) FROM requests WHERE closed_at IS NOT NULL AND closed_at<=? AND closed_at>?',(now()-link*DAY,now()-current['closedLinkDays']*DAY)).fetchone()[0],effectiveAt=iso(now()+DAY),confirmationRequired=photo<current['photoRetentionDays'] or link<current['closedLinkDays'])

@bp.post('/api/v1/admin/settings/retention-preview')
def retention_preview():
    p=body({'photoRetentionDays','closedLinkDays'})
    with connect() as c:return ok(retention(c,p))

@bp.patch('/api/v1/admin/settings')
def update_settings():
    p=body(SETTINGS_FIELDS|{'expectedVersion','confirmRetentionReduction'})
    with transaction() as c:
        require_staff(True,c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        r=c.execute('SELECT * FROM settings WHERE id=1').fetchone();version(p,r)
        current=settings(c);values=current.copy()
        for k in SETTINGS_FIELDS & set(p):
            if k in ('intakeAccepting','emailDeliveryEnabled'):values[k]=boolean(p[k],k)
            elif k=='notificationEmails':values[k]=sorted(set(email(x,'notificationEmails') for x in unique_array(p[k],k,None,5)))
            elif k in ('photoRetentionDays','closedLinkDays'):values[k]=integer(p[k],k,1,730 if k=='photoRetentionDays' else 365)
            else:values[k]=text(p[k],k,1,300 if k=='responseExpectation' else 280,True)
        if not values['intakeAccepting'] and not values['intakePauseMessage']:fail('intakePauseMessage','Explain how customers can contact the shop.')
        if values['emailDeliveryEnabled'] and c.execute("SELECT state FROM integration_secrets WHERE name='gmail'").fetchone()[0]!='connected':raise ApiError('SENDER_DISCONNECTED',409)
        pending=json.loads(r['pending_retention']) if r['pending_retention'] else None
        reductions=any(values[k]<current[k] for k in ('photoRetentionDays','closedLinkDays'))
        if reductions:
            if p.get('confirmRetentionReduction') is not True:fail('confirmRetentionReduction','Review and confirm the retention reduction.')
            pending={k:values[k] for k in ('photoRetentionDays','closedLinkDays')};pending['effectiveAt']=iso(now()+DAY)
            for k in ('photoRetentionDays','closedLinkDays'):
                if values[k]<current[k]:values[k]=current[k]
        elif {'photoRetentionDays','closedLinkDays'} & set(p):pending=None
        save_settings(c,values,pending);updated=c.execute('SELECT * FROM settings WHERE id=1').fetchone()
        audit(c,'settings.updated','settings','1',r['version'],updated['version'])
        result=dict(version=updated['version'],updatedAt=iso(updated['updated_at']))
        if reductions:result['retentionEffectiveAt']=pending['effectiveAt']
        return remember(c,scope,p,result)

@bp.get('/api/v1/admin/hours')
def get_hours():
    with connect() as c:
        r=c.execute("SELECT * FROM hours WHERE location='bel_air'").fetchone()
        return ok(dict(version=r['version'],timezone=r['timezone'],location=r['location'],days=json.loads(r['days']),updatedAt=iso(r['updated_at'])))

@bp.put('/api/v1/admin/hours')
def put_hours():
    p=body({'expectedVersion','days'});validate_hours(p.get('days'))
    with transaction() as c:
        require_staff(True,c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        r=c.execute("SELECT * FROM hours WHERE location='bel_air'").fetchone();version(p,r)
        stamp=now();c.execute("UPDATE hours SET days=?,version=version+1,updated_at=? WHERE location='bel_air'",(json.dumps(p['days']),stamp));audit(c,'hours.updated','hours','bel_air',r['version'],r['version']+1)
        return remember(c,scope,p,dict(version=r['version']+1,updatedAt=iso(stamp)))

NOTICE_FIELDS={'locations','message','reopenText','startsAt','endsAt'}

@bp.get('/api/v1/admin/notices')
def notices():
    with connect() as c:
        state=request.args.get('state','all');enum(state,{'scheduled','active','expired','all'},'state')
        location=request.args.get('location') or None
        where=['deleted_at IS NULL'];args=[]
        if state!='all':
            where.append("(CASE WHEN starts_at>? THEN 'scheduled' WHEN ends_at<=? THEN 'expired' ELSE 'active' END)=?")
            stamp=now();args.extend([stamp,stamp,state])
        if location:
            enum(location,{'bel_air','dundalk'},'location')
            where.append('EXISTS (SELECT 1 FROM json_each(notices.locations) WHERE value=?)');args.append(location)
        return ok(paginate(c,'notices',notice_view,' AND '.join(where),args,filters={'state':state,'location':location}))

@bp.post('/api/v1/admin/notices/preview')
def preview_notice():
    p=notice_input(body(NOTICE_FIELDS))
    with connect() as c:
        replaces=[r['id'] for r in c.execute('SELECT * FROM notices WHERE deleted_at IS NULL AND starts_at<=? AND ends_at>?',(now(),now())) if set(json.loads(r['locations']))&set(p['locations'])]
    return ok(dict(locationIds=p['locations'],banner=dict(message=p['message'],reopenText=p['reopenText']),startsAt=iso(p['startsAt']),endsAt=iso(p['endsAt']),replacesActiveNoticeIds=replaces))

@bp.post('/api/v1/admin/notices')
def create_notice():
    p=notice_input(body(NOTICE_FIELDS))
    with transaction() as c:
        require_staff(True,c);scope=g.member['id'];prior=replay(c,scope,p)
        if prior:return prior
        ident=uid();stamp=now()
        c.execute('INSERT INTO notices VALUES(?,1,?,?,?,?,?,?,?,?,?,NULL)',(ident,json.dumps(p['locations']),p['message'],p['reopenText'],p['startsAt'],p['endsAt'],g.member['id'],g.member['id'],stamp,stamp));audit(c,'notice.created','notice',ident,None,1)
        return remember(c,scope,p,notice_view(row(c,'notices',ident)),201,ident)

@bp.route('/api/v1/admin/notices/<ident>',methods=['GET','PATCH','DELETE'])
def edit_notice(ident):
    if request.method=='GET':
        with connect() as c:
            r=row(c,'notices',ident)
            if r['deleted_at']:raise ApiError('NOT_FOUND',404)
            return ok(notice_view(r))
    p=body(NOTICE_FIELDS|{'expectedVersion'} if request.method=='PATCH' else {'expectedVersion'})
    with transaction() as c:
        require_staff(True,c);scope=g.member['id']
        if request.method=='PATCH':
            prior=replay(c,scope,p)
            if prior:return prior
        r=row(c,'notices',ident);version(p,r)
        if r['deleted_at']:raise ApiError('NOT_FOUND',404)
        if request.method=='DELETE':
            c.execute('UPDATE notices SET deleted_at=?,version=version+1,updated_at=?,updated_by=? WHERE id=?',(now(),now(),g.member['id'],ident));audit(c,'notice.deleted','notice',ident,r['version'],r['version']+1)
            return ok(status=204)
        prior=dict(r);prior['locations']=json.loads(prior['locations']);data=notice_input(p,prior)
        c.execute('UPDATE notices SET locations=?,message=?,reopen_text=?,starts_at=?,ends_at=?,version=version+1,updated_at=?,updated_by=? WHERE id=?',(json.dumps(data['locations']),data['message'],data['reopenText'],data['startsAt'],data['endsAt'],now(),g.member['id'],ident));audit(c,'notice.updated','notice',ident,r['version'],r['version']+1)
        return remember(c,scope,p,notice_view(row(c,'notices',ident)))

@bp.get('/api/v1/admin/audit')
def audit_list():
    clauses=[];args=[]
    for field,column in [('requestId','entity_id'),('actorId','actor_id'),('action','action')]:
        if request.args.get(field):clauses.append(column+'=?');args.append(request.args[field])
    with connect() as c:
        project=lambda r:dict(id=r['id'],at=iso(r['created_at']),actorId=r['actor_id'],action=r['action'],entityType=r['entity_type'],entityId=r['entity_id'],fromVersion=r['from_version'],toVersion=r['to_version'],summary=r['summary'])
        return ok(paginate(c,'audit_events',project,' AND '.join(clauses) or '1',args,filters=dict(zip(clauses,args))))
