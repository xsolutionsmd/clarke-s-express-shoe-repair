import json
from datetime import datetime
import pytest
from clarke import core,db,locations
from conftest import staff

def stamp(value):return int(datetime.fromisoformat(value).timestamp()*1000)

@pytest.mark.parametrize('when,state',[('2026-10-20T08:59:59-04:00','closed'),('2026-10-20T09:00:00-04:00','open'),('2026-10-20T16:30:00-04:00','closing_soon'),('2026-10-20T17:00:00-04:00','closed'),('2026-10-24T10:00:00-04:00','open'),('2026-10-24T13:00:00-04:00','closed'),('2026-11-01T12:00:00-05:00','closed'),('2027-03-14T12:00:00-04:00','closed')])
def test_hours_boundaries(app,when,state):
    with app.app_context(),db.connect() as c:
        result=locations.locations(c,stamp(when));assert result['locations'][0]['state']==state
        assert result['locations'][1]['state']=='appointment_only' and result['locations'][1]['weeklyHours'] is None
        assert '410-284-2458' not in json.dumps(result)
        if when=='2026-11-01T12:00:00-05:00':assert result['locations'][0]['nextOpensAt']=='2026-11-03T14:00:00Z'
        if when=='2027-03-14T12:00:00-04:00':assert result['locations'][0]['nextOpensAt']=='2027-03-16T13:00:00Z'

def test_offset_fold_gap_and_unknown_regular_hours(app):
    for value in ('2027-03-14T02:30:00-05:00','2027-03-14T02:30:00-04:00','2026-11-01T01:30:00-06:00','2027-01-01T09:00:00Z'):
        with pytest.raises(core.ApiError):locations.local_instant(value,'startsAt')
    first=locations.local_instant('2026-11-01T01:30:00-04:00','startsAt');second=locations.local_instant('2026-11-01T01:30:00-05:00','startsAt');assert second-first==3600000
    with app.app_context(),db.transaction() as c:
        days=[None]*7;days[0]={'open':'01:30','close':'03:30'};c.execute('UPDATE hours SET days=?',(json.dumps(days),))
        assert locations.locations(c,stamp('2026-11-01T01:00:00-04:00'))['locations'][0]['state']=='unknown'

def test_closure_union_newest_and_midday_reopen(app):
    _,_,member=staff(app)
    with app.app_context(),db.transaction() as c:
        for ident,start,end,updated in [('older','09:00','12:00',1),('newer','09:30','10:00',2)]:
            c.execute('INSERT INTO notices VALUES(?,1,?,?,?,?,?,?,?,?,?,NULL)',(ident,'["bel_air"]',ident,None,stamp('2026-10-20T'+start+':00-04:00'),stamp('2026-10-20T'+end+':00-04:00'),member,member,1,updated))
        r=locations.locations(c,stamp('2026-10-20T09:45:00-04:00'))
        assert r['locations'][0]['activeNotice']['message']=='newer'
        assert r['locations'][0]['nextOpensAt']=='2026-10-20T16:00:00Z'
        assert locations.locations(c,stamp('2026-10-20T12:00:00-04:00'))['locations'][0]['state']=='open'
        c.execute('UPDATE hours SET days=?',(json.dumps([None]*7),))
        assert locations.locations(c,stamp('2026-10-21T12:00:00-04:00'))['locations'][0]['nextOpensAt'] is None
