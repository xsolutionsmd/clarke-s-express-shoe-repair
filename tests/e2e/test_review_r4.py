"""Round 4 browser regressions; isolated synthetic candidate only."""
import io
import json
import re
import time
import uuid
from PIL import Image
from playwright.sync_api import expect
import seed_sessions
from conftest import BASE, mutate, read
from test_flows import fill, attach, receipt, photo, api_request, find_request, ui_offer


def nav(page, name):
    menu=page.get_by_role('button',name='Menu',exact=True)
    if menu.is_visible() and menu.get_attribute('aria-expanded')!='true':menu.click()
    page.locator('#admin-nav').get_by_role('link',name=name,exact=True).click()


def setup_request(page):
    page.goto('/admin/requests');data,body=api_request(page)
    return find_request(page,data['reference']),data,body


def draft_state(page,member,key):
    return page.evaluate('({member,key})=>JSON.parse(sessionStorage.getItem("clarke.staff."+member)).data[key]',dict(member=member,key=key))


def test_failed_logout_clears_privacy_and_requires_retry(page,admin):
    ident,_,_=setup_request(page);page.goto('/admin/requests/'+ident)
    page.get_by_label('Add an internal note').fill('Private unsaved logout test')
    page.route('**/api/v1/admin/logout',lambda route:route.fulfill(status=503,json={'error':{'code':'DATABASE_BUSY','message':'Retry later.'}}))
    page.get_by_role('button',name='Sign out',exact=True).click()
    expect(page.get_by_text(re.compile('Sign-out could not be confirmed'))).to_be_visible()
    assert not page.evaluate('Object.keys(sessionStorage).some(k=>k.startsWith("clarke.staff"))')
    expect(page.get_by_text('Private unsaved logout test')).to_have_count(0)
    assert read(page,'/admin/session')['status']==200
    page.reload();expect(page.get_by_role('button',name='Retry sign out')).to_be_visible()
    page.unroute('**/api/v1/admin/logout');page.get_by_role('button',name='Retry sign out').click()
    expect(page.get_by_text(re.compile('You’re signed out'))).to_be_visible()
    assert read(page,'/admin/session')['status']==401


def test_valid_last_seconds_photo_draft_keeps_attachment(page):
    fill(page);attach(page,1)
    before=page.evaluate('JSON.parse(sessionStorage.getItem("clarke.intake")).data')
    page.evaluate('''()=>{const v=JSON.parse(sessionStorage.getItem('clarke.intake'));v.data.draft.expiresAt=new Date(Date.now()+30000).toISOString();sessionStorage.setItem('clarke.intake',JSON.stringify(v));}''')
    def near_expiry(route):
        response=route.fetch();body=response.json()
        body['data']['expiresAt']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime(time.time()+30))
        route.fulfill(response=response,json=body)
    page.route('**/api/v1/drafts/'+before['draft']['id'],near_expiry)
    page.reload();expect(page.get_by_text('Photo attached',exact=True)).to_be_visible()
    page.locator('.request-form button[type="submit"]').click();receipt(page)
    with seed_sessions.database() as c:
        row=c.execute('SELECT request_id,draft_id FROM photos WHERE id=?',(before['photos'][0]['photoId'],)).fetchone()
        assert row['request_id'] and row['draft_id']==before['draft']['id']


def test_expired_photo_draft_requires_reattachment(page):
    fill(page);attach(page,1);saved=page.evaluate('JSON.parse(sessionStorage.getItem("clarke.intake")).data')
    with seed_sessions.database() as c:c.execute('UPDATE drafts SET expires_at=? WHERE id=?',(int(time.time()*1000)-1,saved['draft']['id']))
    page.locator('.request-form button[type="submit"]').click()
    expect(page.get_by_text(re.compile('This photo expired after 24 hours'))).to_be_visible()
    assert page.locator('.receipt').count()==0
    page.get_by_role('button',name='Remove shoe-0.jpg').click();attach(page,1)
    page.locator('.request-form button[type="submit"]').click();receipt(page)
    with seed_sessions.database() as c:
        row=c.execute('SELECT request_id FROM photos WHERE id=?',(saved['photos'][0]['photoId'],)).fetchone()
        assert row is None or row['request_id'] is None


def test_clear_during_processing_cancels_submit_and_new_form_works(page):
    submit=fill(page)
    pattern=re.compile(r'/api/v1/drafts/[^/]+/photos/[^/?]+$')
    page.route(pattern,lambda route:route.fulfill(json={'data':{'photoId':route.request.url.rsplit('/',1)[-1],'state':'processing'}}))
    page.locator('#photo-input').set_input_files(photo())
    expect(page.get_by_text('Preparing photo',exact=True)).to_be_visible()
    submit.click();expect(page.get_by_role('button',name='Finishing photo uploads')).to_be_visible()
    page.once('dialog',lambda dialog:dialog.accept());page.get_by_role('button',name='Clear form',exact=True).click()
    expect(page.get_by_label('Your name',exact=True)).to_have_value('')
    expect(page.locator('.photo-item')).to_have_count(0);page.unroute(pattern)
    # No reload: same module must permit a replacement submission.
    page.locator('input[name="location"][value="bel_air"]').check();page.locator('input[name="itemType"][value="boots"]').check()
    page.get_by_label('Describe the item and the problem').fill('New form after cancelling photo conversion wait.')
    page.get_by_label('Your name',exact=True).fill('After Clear '+uuid.uuid4().hex[:8])
    page.get_by_label('Email',exact=True).fill(uuid.uuid4().hex+'@example.test')
    page.locator('.request-form button[type="submit"]').click();receipt(page)


def test_delayed_admin_detail_cannot_replace_new_route(page,admin):
    ident,_,_=setup_request(page);held=[]
    page.route('**/api/v1/admin/requests/'+ident,lambda route:held.append((route,route.fetch())))
    page.evaluate('id=>{const a=document.createElement("a");a.href="/admin/requests/"+id;a.dataset.nav="";document.body.append(a);a.click();a.remove()}',ident)
    expect(page.locator('#admin-main')).to_contain_text('Loading');page.wait_for_timeout(100)
    nav(page,'Settings');expect(page.get_by_role('heading',name='Settings',exact=True)).to_be_visible();assert held
    for route,response in held:route.fulfill(response=response)
    page.wait_for_timeout(150)
    expect(page.get_by_role('heading',name='Settings',exact=True)).to_be_visible()
    expect(page.get_by_label('Add an internal note')).to_have_count(0)
    if page.viewport_size['width']<1000:
        expect(page.get_by_role('button',name='Menu',exact=True)).to_have_attribute('aria-expanded','false')
    nav(page,'Hours');expect(page.get_by_role('heading',name='Hours',exact=True)).to_be_visible()


def lookup(page,data,body):
    page.locator('input[name="reference"]').fill(data['reference']);page.locator('input[name="value"]').fill(body['contact']['email'])
    page.get_by_role('button',name='Find my repair',exact=True).click()
    expect(page.locator('.status-ref')).to_contain_text(data['reference'])


def test_forget_clears_history_and_discards_old_events(page,admin):
    ident,first,_=setup_request(page);second,second_body=api_request(page)
    with seed_sessions.database() as c:
        stamp=int(time.time()*1000)
        for n in range(70):c.execute('INSERT INTO request_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),ident,'status_changed',None,'new','A-only private update '+str(n),'customer',None,None,None,1,stamp+n))
    page.goto('/repair-status#token='+first['statusUrl'].split('#token=')[1]);expect(page.locator('.status-ref')).to_contain_text(first['reference'])
    page.get_by_role('button',name='Show earlier updates').click();expect(page.get_by_role('button',name='Show earlier updates')).to_be_enabled()
    held=[];page.route('**/api/v1/status/events?**',lambda route:held.append((route,route.fetch())))
    page.get_by_role('button',name='Show earlier updates').click();expect(page.get_by_role('button',name='Loading',exact=True)).to_be_visible()
    page.get_by_role('button',name='Forget this link in this tab').click();lookup(page,second,second_body);assert held
    for route,response in held:route.fulfill(response=response)
    page.wait_for_timeout(150)
    assert 'A-only private update' not in page.locator('#status-app').inner_text()
    assert first['reference'] not in page.locator('#status-app').inner_text()
    expect(page.get_by_role('button',name='Show earlier updates')).to_have_count(0)


def test_reply_draft_survives_same_link_reload_but_not_forget(page,admin):
    ident,data,_=setup_request(page);ui_offer(page,ident);page.goto(data['statusUrl'])
    page.get_by_role('button',name='Please call me',exact=True).click()
    page.get_by_label('Phone number to call').fill('2025550123')
    page.route('**/api/v1/status/responses',lambda route:route.fulfill(status=503,json={'error':{'code':'DATABASE_BUSY','message':'Retry reply later.'}}))
    page.get_by_role('button',name='Request a call',exact=True).click();expect(page.get_by_text('Retry reply later.',exact=True)).to_be_visible()
    saved=page.evaluate('Object.entries(sessionStorage).filter(([k])=>k.startsWith("clarke.resp."))');assert len(saved)==1
    page.reload();expect(page.get_by_label('Phone number to call')).to_have_value('2025550123')
    assert page.evaluate('Object.entries(sessionStorage).filter(([k])=>k.startsWith("clarke.resp."))')==saved
    page.get_by_role('button',name='Forget this link in this tab',exact=True).click()
    assert page.evaluate('Object.keys(sessionStorage).filter(k=>k.startsWith("clarke.resp."))')==[]


def test_refresh_failure_keeps_data_and_allows_retry(page):
    page.goto('/');data,_=api_request(page);page.goto('/repair-status#token='+data['statusUrl'].split('#token=')[1])
    expect(page.locator('#status-title')).to_have_text('Received')
    page.route('**/api/v1/status',lambda route:route.fulfill(status=503,json={'error':{'code':'DATABASE_BUSY','message':'Try again.'}}))
    page.get_by_role('button',name='Refresh',exact=True).click();expect(page.get_by_text(re.compile('Could not refresh'))).to_be_visible()
    expect(page.locator('.status-ref')).to_contain_text(data['reference']);expect(page.get_by_role('button',name='Refresh',exact=True)).to_be_enabled()
    page.unroute('**/api/v1/status');page.get_by_role('button',name='Refresh',exact=True).click()
    expect(page.get_by_text(re.compile('Could not refresh'))).to_have_count(0);expect(page.get_by_role('button',name='Refresh',exact=True)).to_be_enabled()


def test_panel_failures_retry_instead_of_empty_and_401(page,admin):
    ident,_,_=setup_request(page);base='/api/v1/admin/requests/'+ident
    assert mutate(page,'/admin/requests/'+ident+'/notes',{'expectedVersion':1,'text':'Existing important synthetic note.'})['status']==201
    for name in ('notes','events','offers'):page.route('**'+base+'/'+name+'?**',lambda route:route.fulfill(status=503,json={'error':{'code':'DATABASE_BUSY','message':'Retry later.'}}))
    page.goto('/admin/requests/'+ident)
    for label in ('Notes','History','Offer history'):expect(page.get_by_text(re.compile(label+' could not be loaded'))).to_be_visible()
    expect(page.get_by_text('No notes yet.',exact=True)).to_have_count(0);expect(page.get_by_text('No history yet.',exact=True)).to_have_count(0)
    for name,label in (('notes','notes'),('events','history'),('offers','offer history')):
        page.unroute('**'+base+'/'+name+'?**');page.get_by_role('button',name='Retry '+label,exact=True).click()
        expect(page.get_by_role('button',name='Retry '+label,exact=True)).to_have_count(0)
    expect(page.get_by_text('Existing important synthetic note.',exact=True)).to_be_visible()
    page.route('**'+base+'/notes?**',lambda route:route.fulfill(status=401,json={'error':{'code':'SESSION_EXPIRED','message':'Sign in again.'}}))
    page.reload();expect(page.locator('.session-banner')).to_be_visible();expect(page.get_by_role('button',name='Retry notes')).to_be_visible()


def test_retention_preserve_replace_and_explicit_cancel(page,admin):
    page.goto('/admin/settings');settings=read(page,'/admin/settings')['body']['data']
    assert mutate(page,'/admin/settings',{'expectedVersion':settings['version'],'photoRetentionDays':90,'closedLinkDays':60,'confirmRetentionReduction':True},'PATCH')['status']==200
    pending=read(page,'/admin/settings')['body']['data']['pendingRetention'];page.reload()
    expect(page.get_by_text(re.compile('Scheduled change: photos 90 days'))).to_be_visible()
    page.get_by_label('Response target (staff only)',exact=False).fill('Unrelated planning edit');page.get_by_role('button',name='Save settings',exact=True).click()
    expect(page.get_by_text('Settings saved.',exact=True)).to_be_visible();assert read(page,'/admin/settings')['body']['data']['pendingRetention']==pending
    page.get_by_label('Retention change',exact=True).select_option('change');page.get_by_label('Delete photos after closing, days').fill('80')
    page.get_by_role('button',name='Preview impact',exact=True).click();expect(page.get_by_text(re.compile('would be deleted'))).to_be_visible()
    page.locator('#set-confirm-reduce').check();page.get_by_role('button',name='Save settings',exact=True).click()
    expect(page.get_by_text(re.compile('Scheduled change: photos 80 days'))).to_be_visible()
    assert read(page,'/admin/settings')['body']['data']['pendingRetention']['photoRetentionDays']==80
    page.get_by_label('Retention change',exact=True).select_option('cancel');page.get_by_role('button',name='Save settings',exact=True).click()
    expect(page.get_by_text('No scheduled retention change.',exact=True)).to_be_visible();assert read(page,'/admin/settings')['body']['data']['pendingRetention'] is None


def test_hours_stale_draft_comparison_then_deliberate_reapply(page,admin):
    page.goto('/admin/locations');page.get_by_label('Tuesday closes',exact=True).fill('16:00')
    old=draft_state(page,admin['memberId'],'hours')['baseVersion'];current=read(page,'/admin/hours')['body']['data'];current['days'][2]['open']='10:00'
    assert mutate(page,'/admin/hours',{'expectedVersion':current['version'],'days':current['days']},'PUT')['status']==200
    page.reload();compare=page.get_by_role('region',name='Compare current values and your draft')
    expect(compare).to_contain_text('10:00 to 17:00');expect(compare).to_contain_text('09:00 to 16:00')
    assert draft_state(page,admin['memberId'],'hours')['baseVersion']==old
    page.get_by_role('button',name='Save hours',exact=True).click();assert read(page,'/admin/hours')['body']['data']['days'][2]['open']=='10:00'
    compare.get_by_role('button',name='Reapply my draft').click();page.get_by_label('Tuesday opens',exact=True).fill('10:00')
    page.get_by_role('button',name='Save hours',exact=True).click();expect(page.get_by_text('Hours saved. The website shows them right away.',exact=True)).to_be_visible()
    assert read(page,'/admin/hours')['body']['data']['days'][2]=={'open':'10:00','close':'16:00'}


def test_settings_load_latest_and_reload_keep_old_base(page,admin):
    page.goto('/admin/settings');page.get_by_label('Response target (staff only)',exact=False).fill('My draft response target')
    old=draft_state(page,admin['memberId'],'settings')['baseVersion'];data=read(page,'/admin/settings')['body']['data']
    assert mutate(page,'/admin/settings',{'expectedVersion':data['version'],'responseExpectation':'Other staff target'},'PATCH')['status']==200
    page.get_by_role('button',name='Save settings',exact=True).click();page.get_by_role('button',name='Load latest details',exact=True).click()
    compare=page.get_by_role('region',name='Compare current values and your draft');expect(compare).to_contain_text('Other staff target');expect(compare).to_contain_text('My draft response target')
    assert draft_state(page,admin['memberId'],'settings')['baseVersion']==old
    page.reload();expect(compare).to_contain_text('Other staff target');assert draft_state(page,admin['memberId'],'settings')['baseVersion']==old
    page.get_by_role('button',name='Reapply my draft').click();page.get_by_role('button',name='Save settings',exact=True).click()
    expect(page.get_by_text('Settings saved.',exact=True)).to_be_visible();assert read(page,'/admin/settings')['body']['data']['responseExpectation']=='My draft response target'


def test_request_restored_draft_keeps_version_until_reapply(page,admin):
    ident,_,_=setup_request(page);page.goto('/admin/requests/'+ident)
    page.get_by_label('Status',exact=True).select_option('reviewing');page.get_by_label('Message to the customer',exact=False).first.fill('My draft public message')
    old=draft_state(page,admin['memberId'],'req:'+ident+':status')['baseVersion']
    assert mutate(page,'/admin/requests/'+ident,{'expectedVersion':old,'customerMessage':'Current concurrent message'},'PATCH')['status']==200
    page.reload();compare=page.get_by_role('region',name='Compare current values and your draft')
    expect(compare).to_contain_text('Current concurrent message');expect(compare).to_contain_text('My draft public message')
    assert draft_state(page,admin['memberId'],'req:'+ident+':status')['baseVersion']==old
    page.get_by_role('button',name='Update status',exact=True).click();assert read(page,'/admin/requests/'+ident)['body']['data']['customerMessage']=='Current concurrent message'
    compare.get_by_role('button',name='Reapply my draft').click();page.get_by_role('button',name='Update status',exact=True).click()
    expect(page.get_by_text(re.compile('Status changed to'))).to_be_visible();assert read(page,'/admin/requests/'+ident)['body']['data']['customerMessage']=='My draft public message'


def test_new_status_draft_during_own_note_refresh_uses_confirmed_version(page,admin):
    ident,_,_=setup_request(page);page.goto('/admin/requests/'+ident)
    expect(page.get_by_label('Add an internal note')).to_be_visible()
    held=[];path='**/api/v1/admin/requests/'+ident
    page.route(path,lambda route:held.append((route,route.fetch())))
    page.get_by_label('Add an internal note').fill('My own confirmed note before drafting status.')
    with page.expect_response(lambda response:response.url.endswith('/'+ident+'/notes') and response.request.method=='POST'):
        page.get_by_role('button',name='Add note',exact=True).click()
    for _ in range(100):
        if held:break
        page.wait_for_timeout(20)
    assert held
    page.get_by_label('Status',exact=True).select_option('reviewing')
    for route,response in held:route.fulfill(response=response)
    page.unroute(path);expect(page.get_by_text('Note added.',exact=True)).to_be_visible()
    page.get_by_role('button',name='Update status',exact=True).click()
    expect(page.get_by_text(re.compile('Status changed to'))).to_be_visible()
    expect(page.get_by_role('region',name='Compare current values and your draft')).to_have_count(0)


def test_waiting_badge_matches_unanswered_offer(page,admin):
    ident,data,_=setup_request(page);ui_offer(page,ident);page.goto('/admin/requests');page.locator('input[name="filter"][value="waiting"]').check()
    page.get_by_label('Search',exact=True).fill(data['reference']);page.get_by_role('button',name='Search',exact=True).click()
    expect(page.locator('.request-row')).to_have_count(1);expect(page.locator('.request-row')).to_contain_text('Waiting for customer reply')
    assert 'Customer replied' not in page.locator('.request-row').inner_text()
    token=data['statusUrl'].split('#token=')[1];status=read(page,'/status',token)['body']['data']
    assert mutate(page,'/status/responses',{'offerId':status['offer']['id'],'expectedVersion':status['version'],'choice':'accept','phone':None},bearer=token)['status']==200
    page.reload();expect(page.locator('.request-row')).to_have_count(1);assert 'Waiting for customer reply' not in page.locator('.request-row').inner_text()


def test_double_text_header_and_card_controls(page):
    fill(page)
    page.evaluate('''()=>{const values=[...document.body.querySelectorAll('*')].map(el=>[el,getComputedStyle(el).fontSize,getComputedStyle(el).lineHeight]);for(const [el,font,line] of values){el.style.fontSize=parseFloat(font)*2+'px';if(line!=='normal')el.style.lineHeight=parseFloat(line)*2+'px';}}''')
    assert page.evaluate('''()=>{const h=document.querySelector('.header-inner').getBoundingClientRect(),m=document.querySelector('.header-inner>.wordmark').getBoundingClientRect(),b=document.querySelector('.menu-toggle').getBoundingClientRect(),c=document.querySelector('.header-call').getBoundingClientRect();if(innerWidth<1041&&!(m.left>=b.right&&m.right<=c.left&&m.top>=h.top&&m.bottom<=h.bottom))return false;return [...document.querySelectorAll('.request-form input:not([type=radio]):not([type=checkbox]):not([type=file]),.request-form textarea,.request-form select')].filter(x=>x.getClientRects().length&&!x.closest('.honeypot')).every(x=>{const a=x.getBoundingClientRect(),b=x.closest('.request-form').getBoundingClientRect();return a.left>=b.left&&a.right<=b.right;});}''')


def test_portrait_fit_actual_size_and_print_media(page,admin):
    fill(page);out=io.BytesIO();Image.new('RGB',(500,1291),(120,80,40)).save(out,'JPEG')
    page.locator('#photo-input').set_input_files({'name':'portrait.jpg','mimeType':'image/jpeg','buffer':out.getvalue()})
    expect(page.get_by_text(re.compile('Ready,'))).to_be_visible(timeout=30000)
    page.locator('.request-form button[type="submit"]').click();data=receipt(page);ident=find_request(page,data['reference']);page.goto('/admin/requests/'+ident)
    page.set_viewport_size({'width':page.viewport_size['width'],'height':812});page.emulate_media(reduced_motion='reduce')
    page.get_by_role('button',name='Open photo 1 of 1').hover();assert page.locator('.photo-cell img').evaluate('e=>getComputedStyle(e).transform')=='none'
    page.get_by_role('button',name='Open photo 1 of 1').click()
    page.wait_for_function('document.querySelector(".zoom-frame img").naturalHeight===1291')
    assert page.evaluate('''()=>{const f=document.querySelector('.zoom-frame'),i=f.querySelector('img'),a=i.getBoundingClientRect(),b=f.getBoundingClientRect();return a.height<=b.height+1&&a.width<=b.width+1&&f.scrollHeight<=f.clientHeight+1&&getComputedStyle(i).objectFit==='contain'}''')
    page.get_by_role('button',name='Actual size',exact=True).click();assert page.evaluate('document.querySelector(".zoom-frame").scrollHeight>document.querySelector(".zoom-frame").clientHeight')
    page.keyboard.press('Escape');page.evaluate('window.print=()=>{window.__printRequested=true}')
    page.get_by_role('button',name='Print status slip',exact=True).click();page.wait_for_function('window.__printRequested===true');page.emulate_media(media='print')
    slip=page.locator('.print-slip');expect(slip).to_be_visible();expect(slip).to_contain_text(data['reference']);expect(slip).to_contain_text('23 South Main St. (REAR), Burns Alley')
    expect(page.locator('#admin-root')).not_to_be_visible()
    assert page.evaluate('document.querySelector(".print-slip").scrollWidth<=document.querySelector(".print-slip").clientWidth')
    pdf=page.pdf(format='Letter');assert pdf.startswith(b'%PDF-') and len(pdf)>4000
    page.emulate_media(media='screen')


def test_unknown_page_html_recovery_preserves_api_json(page,admin):
    for path in ('/admin/not-a-real-page','/not-a-real-page'):
        response=page.goto(path);assert response.status==404
        expect(page.get_by_role('heading',name='Page not found')).to_be_visible()
        assert page.get_by_role('link',name='Back to the website',exact=True).get_attribute('href')=='/'
    result=page.request.get(BASE+'/api/v1/not-real',headers={'Accept':'text/html'});assert result.status==404 and result.json()['error']['code']=='NOT_FOUND'


def test_reduced_motion_distinct_browser_contexts(browser):
    for mode in ('reduce','no-preference'):
        ctx=browser.new_context(base_url=BASE,viewport={'width':375,'height':812},reduced_motion=mode)
        try:
            page=ctx.new_page();page.goto('/')
            v=page.evaluate('''()=>{const s=getComputedStyle(document.querySelector('[data-reveal]'));return {reduce:matchMedia('(prefers-reduced-motion: reduce)').matches,transition:s.transitionProperty,duration:s.transitionDuration,scroll:getComputedStyle(document.documentElement).scrollBehavior}}''')
            assert v['reduce']==(mode=='reduce')
            if mode=='reduce':
                assert v['scroll']=='auto' and v['transition']=='opacity'
                assert all(float(x.strip().rstrip('s'))<=0.15 for x in v['duration'].split(','))
                assert page.locator('.site-nav').evaluate('e=>getComputedStyle(e).transform')=='none'
                page.locator('.menu-toggle').click();assert 'transform' not in page.locator('.site-nav').evaluate('e=>getComputedStyle(e).transitionProperty')
                page.locator('.menu-toggle').click()
                page.locator('.service-link').first.hover();assert page.locator('.service-photo img').first.evaluate('e=>getComputedStyle(e).transform')=='none'
                assert page.locator('[data-reveal]').evaluate_all('es=>es.every(e=>getComputedStyle(e).transform==="none")')
            else:assert 'transform' in v['transition'] and v['scroll']=='smooth'
        finally:ctx.close()
