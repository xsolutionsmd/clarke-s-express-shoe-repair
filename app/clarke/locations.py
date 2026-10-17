"""New York wall-clock rules and closure unions; Dundalk never has open hours."""
import json
import re
from datetime import datetime, timedelta, timezone
from flask import Blueprint
from .core import ApiError, LOCATIONS, now, iso, ok, fail
from .db import connect
from .validation import NY, text, unique_array

bp=Blueprint('locations',__name__)
BEL_AIR={'id':'bel_air','name':'Bel Air','visitMode':'walk_in','address':'23 South Main St. (REAR), Burns Alley, Bel Air, MD 21014','directionsNote':'Behind Boyd Fulford Pharmacy and The Main Street Tower Restaurant. Public parking is in front of the rear shop.','phoneHref':'tel:+14108368316','smsHref':None,'mapsHref':"https://www.google.com/maps/place/Clarke's+Express+Shoe+Repair/data=!4m2!3m1!1s0x0:0x87b61559389294c5",'repairWorkHere':True}
DUNDALK={'id':'dundalk','name':'Dundalk','visitMode':'appointment_only','address':'6920 Holabird Ave., Dundalk, MD 21222','directionsNote':'By appointment. Call or text to arrange a visit. All repairs are performed in Bel Air.','phoneHref':'tel:+14433863800','smsHref':'sms:+14433863800','mapsHref':"https://www.google.com/maps/place/Clarke's+Express+Shoe+Repair/data=!4m2!3m1!1s0x89c80135e7828f67:0x9af1bbe4049ffff",'repairWorkHere':False}

def validate_hours(days):
    if not isinstance(days,list) or len(days)!=7:fail('days','Provide all seven days.')
    for i,day in enumerate(days):
        if day is None:continue
        if not isinstance(day,dict) or set(day)!={'open','close'}:fail(f'days.{i}')
        for k in ('open','close'):
            if not isinstance(day[k],str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',day[k]):fail(f'days.{i}.{k}','Use HH:mm.')
        if day['close']<=day['open']:fail(f'days.{i}.close','Closing must be after opening.')
    return days

def local_instant(value,field):
    try:
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?(?:[+-]\d\d:\d\d|Z)',value):raise ValueError()
        supplied=datetime.fromisoformat(value.replace('Z','+00:00'))
        actual=supplied.astimezone(NY)
        if actual.replace(tzinfo=None)!=supplied.replace(tzinfo=None) or actual.utcoffset()!=supplied.utcoffset():raise ValueError()
        return int(supplied.timestamp()*1000)
    except (ValueError,TypeError,OverflowError):
        raise ApiError('INVALID_LOCAL_TIME',422,message='Choose a real New York time and its UTC offset.',fields={field:'This time or offset does not exist in New York.'}) from None

def notice_input(p,previous=None):
    prior=previous or {}
    locations=unique_array(p.get('locations',prior.get('locations')),'locations',LOCATIONS,2,1)
    start=local_instant(p['startsAt'],'startsAt') if 'startsAt' in p else prior.get('starts_at')
    end=local_instant(p['endsAt'],'endsAt') if 'endsAt' in p else prior.get('ends_at')
    if start is None:fail('startsAt')
    if end is None or end<=start:fail('endsAt','Ending must be after starting.')
    return dict(locations=locations,message=text(p.get('message',prior.get('message')),'message',1,280),reopenText=text(p.get('reopenText',prior.get('reopen_text')),'reopenText',1,160,True),startsAt=start,endsAt=end)

def notice_view(r,stamp=None):
    stamp=now() if stamp is None else stamp
    return {'id':r['id'],'version':r['version'],'locations':json.loads(r['locations']),'message':r['message'],'reopenText':r['reopen_text'],'startsAt':iso(r['starts_at']),'endsAt':iso(r['ends_at']),'state':'expired' if r['ends_at']<=stamp else 'scheduled' if r['starts_at']>stamp else 'active','createdAt':iso(r['created_at']),'updatedAt':iso(r['updated_at'])}

def wall(day,clock):
    naive=datetime.fromisoformat(day.isoformat()+'T'+clock)
    first=naive.replace(tzinfo=NY,fold=0);second=naive.replace(tzinfo=NY,fold=1)
    if first.utcoffset()!=second.utcoffset() or first.astimezone(timezone.utc).astimezone(NY).replace(tzinfo=None)!=naive:return None
    return int(first.timestamp()*1000)

def intervals(day,days,closures):
    rule=days[(day.weekday()+1)%7]
    if rule is None:return []
    start,end=wall(day,rule['open']),wall(day,rule['close'])
    if start is None or end is None:return None
    pieces=[(start,end)]
    for a,b in closures:
        newer=[]
        for x,y in pieces:
            if b<=x or a>=y:newer.append((x,y))
            else:
                if x<a:newer.append((x,a))
                if b<y:newer.append((b,y))
        pieces=newer
    return pieces

def clock_label(stamp):
    return datetime.fromtimestamp(stamp/1000,NY).strftime('%I:%M %p').lstrip('0').replace(':00','').lower()

def locations(c,stamp=None):
    stamp=now() if stamp is None else stamp
    hour=c.execute("SELECT * FROM hours WHERE location='bel_air'").fetchone()
    try:
        days=validate_hours(json.loads(hour['days'])) if hour else None
    except (ValueError,ApiError,TypeError):days=None
    notices=list(c.execute('SELECT * FROM notices WHERE deleted_at IS NULL AND ends_at>? ORDER BY updated_at DESC,id DESC',(stamp,)))
    active={loc:next((r for r in notices if r['starts_at']<=stamp and loc in json.loads(r['locations'])),None) for loc in LOCATIONS}
    closures=sorted((r['starts_at'],r['ends_at']) for r in notices if 'bel_air' in json.loads(r['locations']))
    local=datetime.fromtimestamp(stamp/1000,NY);date=local.date()
    current=intervals(date,days,closures) if days is not None else None
    end=next((b for a,b in current if a<=stamp<b),None) if current is not None else None
    next_open=None
    if days is not None and end is None:
        for delta in range(367):
            parts=intervals(date+timedelta(days=delta),days,closures)
            if parts:
                next_open=next((max(a,stamp) for a,b in parts if b>stamp),None)
                if next_open is not None:break
    state='unknown' if current is None else 'closed_notice' if active['bel_air'] else 'closing_soon' if end and end-stamp<=1800000 else 'open' if end else 'closed'
    if state=='unknown':state_text='Call before visiting';next_open=None
    elif active['bel_air']:state_text='Closed today'
    elif end:state_text='Open until '+clock_label(end)
    elif next_open:state_text='Closed, opens '+datetime.fromtimestamp(next_open/1000,NY).strftime('%A')+' '+clock_label(next_open)
    else:state_text='Call before visiting'
    def banner(loc):
        r=active[loc]
        return {'id':r['id'],'message':r['message'],'reopenText':r['reopen_text'],'startsAt':iso(r['starts_at']),'endsAt':iso(r['ends_at'])} if r else None
    changes=[stamp+60000]+[x for r in notices for x in (r['starts_at'],r['ends_at']) if x>stamp]
    if end:changes += [end]+([end-1800000] if end-1800000>stamp else [])
    if next_open and next_open>stamp:changes.append(next_open)
    return {'asOf':iso(stamp),'validUntil':iso(min(changes)),'timezone':'America/New_York','hoursVersion':hour['version'] if hour else None,'locations':[BEL_AIR|dict(weeklyHours=days,state=state,stateText=state_text,closesAt=iso(end),nextOpensAt=iso(next_open),activeNotice=banner('bel_air')),DUNDALK|dict(weeklyHours=None,state='appointment_only',stateText='By appointment, call or text 443-386-3800',closesAt=None,nextOpensAt=None,activeNotice=banner('dundalk'))]}

def route_message(location,pickup=False):
    if location=='dundalk':return 'Call or text 443-386-3800 to arrange a Dundalk visit. All repairs are performed in Bel Air.'
    if pickup:return 'Collect your item at 23 South Main St. (REAR), Burns Alley, Bel Air. Call 410-836-8316 before visiting if you need to check the hours.'
    return 'Bring your item to 23 South Main St. (REAR), Burns Alley, Bel Air. Call 410-836-8316 before visiting if you need to check the hours.'

@bp.get('/api/v1/locations')
def get_locations():
    with connect() as c:return ok(locations(c))
