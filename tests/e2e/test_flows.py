"""Real frontend + candidate API flows. Each parametrized context is 1440 or 375px.

Google/Gmail acceptance is deliberately separate: sessions are direct DB fixtures,
emails are previews, and provider failure semantics are exercised by backend tests.
"""
import io
import json
from pathlib import Path
import re
import time
import uuid
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import pytest
from PIL import Image
from playwright.sync_api import expect
import seed_sessions
from conftest import BASE,mutate,read

def photo(name='shoe.jpg'):
    out=io.BytesIO();Image.new('RGB',(96,72),(120,70,48)).save(out,'JPEG')
    return dict(name=name,mimeType='image/jpeg',buffer=out.getvalue())

def fill(page,location='bel_air',address=None):
    page.goto('/repair-request')
    page.locator(f'input[name="location"][value="{location}"]').check()
    page.locator('input[name="itemType"][value="boots"]').check()
    page.locator('input[name="workTypes"][value="soles_heels"]').check()
    page.get_by_label('Describe the item and the problem').fill('Synthetic test: the boot heel has separated from the sole.')
    page.get_by_label('Your name',exact=True).fill('Synthetic Browser Customer')
    page.get_by_label('Email',exact=True).fill(address or 'browser-'+uuid.uuid4().hex[:8]+'@example.test')
    return page.locator('.request-form button[type="submit"]')

def receipt(page):
    page.wait_for_url('**/repair-request/complete',timeout=30000)
    result=page.evaluate("JSON.parse(sessionStorage.getItem('clarke.receipt')).data")
    assert result['reference'].startswith('CLK-')
    return result

def attach(page,number=3):
    page.locator('#photo-input').set_input_files([photo(f'shoe-{n}.jpg') for n in range(number)])
    page.wait_for_function("""n => { const x=JSON.parse(sessionStorage.getItem('clarke.intake')||'null'); return x?.data?.photos?.filter(p=>p.state==='ready').length===n; }""",arg=number,timeout=40000)

def staff_page(browser,role='admin',width=1440):
    ctx=browser.new_context(base_url=BASE,viewport={'width':width,'height':900},reduced_motion='reduce')
    identity=seed_sessions.seed(role);ctx.add_cookies([identity['cookie']]);page=ctx.new_page();page.goto('/admin/requests')
    expect(page.get_by_role('heading',name='Requests',exact=True)).to_be_visible()
    return ctx,page,identity

def find_request(page,ref):
    data=read(page,'/admin/requests?filter=all&q='+ref)['body']['data']['items']
    assert len(data)==1
    return data[0]['id']

def ui_offer(page,ident,visit=False):
    page.goto('/admin/requests/'+ident)
    if visit:
        page.locator('input[name="offerKind"][value="visit"]').check()
        page.get_by_label('Why you need to see it').fill('Please bring the synthetic item in so we can assess the repair.')
        page.get_by_role('button',name='Ask customer to bring it in',exact=True).click()
        page.get_by_role('dialog').get_by_role('button',name='Send request to visit',exact=True).click()
        expect(page.get_by_text('Visit request sent to the customer’s status page.',exact=True)).to_be_visible()
    else:
        page.get_by_label('Amount in dollars',exact=True).fill('12.34')
        page.get_by_label('What the estimate covers').fill('Replace the synthetic boot sole after inspection.')
        page.get_by_role('button',name='Send estimate',exact=True).click()
        page.get_by_role('dialog').get_by_role('button',name='Send estimate',exact=True).click()
        expect(page.get_by_text('Estimate sent to the customer’s status page.',exact=True)).to_be_visible()

def api_request(page,location='bel_air',phone=None):
    d=mutate(page,'/drafts',{})['body']['data']
    p=dict(draftId=d['draftId'],itemType='boots',workTypes=['soles_heels'],description='Synthetic browser request for boot sole repair.',brandAge=None,location=location,neededBy=None,contact=dict(name='Synthetic Browser Setup',email=uuid.uuid4().hex[:8]+'@example.test',phone=phone,preferred='email'),photoIds=[],consentVersion='repair-intake-v1',website='')
    r=mutate(page,'/requests',p,draft=d['draftToken']);assert r['status']==201,r
    return r['body']['data'],p

def test_bel_air_three_photos_receipt_emails_refresh_back(page,context,browser):
    submit=fill(page);attach(page,3);submit.click();data=receipt(page)
    expect(page.get_by_text(data['reference'],exact=False).first).to_be_visible()
    page.reload();expect(page.get_by_text(data['reference'],exact=False).first).to_be_visible()
    page.go_back();expect(page.locator('.request-form')).to_have_count(0)
    staff_ctx,staff,_=staff_page(browser,width=context.pages[0].viewport_size['width'])
    try:
        ident=find_request(staff,data['reference']);detail=read(staff,'/admin/requests/'+ident)['body']['data'];assert len(detail['photos'])==3
        out=read(staff,'/admin/outbox?requestId='+ident)['body']['data']['items'];assert {r['kind'] for r in out}=={'customer_received','staff_new_request'} and all(r['status']=='preview_only' for r in out)
    finally:staff_ctx.close()


def test_walkin_phone_only_text_link_and_inbox_filters(page,admin):
    page.goto('/admin/requests/new')
    page.get_by_label('Customer name',exact=True).fill('Synthetic Phone Walk-in')
    page.locator('input[name="phone"]').fill('2025550123')
    page.locator('input[name="itemType"][value="shoes"]').check()
    page.get_by_label('Description',exact=True).fill('Synthetic walk-in: replace a damaged shoe heel.')
    page.get_by_role('button',name='Create ticket',exact=True).click()
    page.wait_for_url(re.compile('/admin/requests/[0-9a-f-]{36}$'))
    ident=page.url.rsplit('/',1)[1]
    detail=read(page,'/admin/requests/'+ident)['body']['data']
    assert detail['source']=='walk_in' and detail['contact']['email'] is None and not detail['photos']
    page.get_by_role('button',name='Text status link',exact=True).click()
    link=page.get_by_role('link',name='Open messages',exact=True)
    expect(link).to_be_visible()
    assert link.get_attribute('href').startswith('sms:+12025550123') and 'body=' in link.get_attribute('href')
    # Inspect destination only. Never open an external messaging app.
    page.goto('/admin/requests')
    page.locator('input[name="filter"][value="in_shop"]').check()
    page.get_by_label('Search',exact=True).fill(detail['reference'])
    page.get_by_role('button',name='Search',exact=True).click()
    expect(page.locator('.request-row')).to_have_count(1)
    assert detail['reference'] not in page.url
    page.locator('input[name="filter"][value="ready"]').check()
    expect(page.get_by_text('No matching requests',exact=True)).to_be_visible()


def test_hours_editor_validation_and_saved_state(page,admin):
    page.goto('/admin/locations')
    expect(page.get_by_role('heading',name='Hours',exact=True)).to_be_visible()
    page.get_by_label('Tuesday closes',exact=True).fill('08:00')
    page.get_by_role('button',name='Save hours',exact=True).click()
    expect(page.get_by_text(re.compile('Closing time must be after opening time')).first).to_be_visible()
    expect(page.get_by_label('Tuesday closes',exact=True)).to_be_focused()
    page.get_by_label('Tuesday closes',exact=True).fill('17:00')
    page.get_by_role('button',name='Save hours',exact=True).click()
    expect(page.get_by_text('Hours saved. The website shows them right away.',exact=True)).to_be_visible()
    assert read(page,'/admin/hours')['body']['data']['days'][2]==dict(open='09:00',close='17:00')
    assert page.get_by_text(re.compile('There are no Dundalk hours to set')).count()==1


def test_uninvited_and_expired_google_sessions_rejected_in_real_http(page,context):
    identity=seed_sessions.seed('viewer',expired=True);context.add_cookies([identity['cookie']])
    page.goto('/admin/requests');page.wait_for_url('**/admin/login')
    assert read(page,'/admin/requests')['status']==401
    context.clear_cookies()
    page.goto('/admin/login');expect(page.get_by_role('heading').first).to_be_visible()
    for path in ('/api/v1/admin/team/members','/api/v1/admin/email/connection','/api/v1/admin/settings'):
        assert page.evaluate('async path=>(await fetch(path)).status',path)==401
    for path in ('/api/test/session','/__e2e/login','/api/v1/test/seed'):
        assert page.evaluate('async path=>(await fetch(path)).status',path)==404


def test_failed_delivery_fixture_keeps_request_and_explains_disconnected_sender(page,browser):
    # A failure-state fixture tests rendering only. Transport/retry execution is
    # tested with process-local injection in app/tests/test_mail.py, never runtime.
    fill(page).click();data=receipt(page)
    staff_ctx,staff,_=staff_page(browser,width=page.viewport_size['width'])
    try:
        ident=find_request(staff,data['reference'])
        with seed_sessions.database() as c:
            c.execute("UPDATE requests SET is_synthetic=1 WHERE id=?",(ident,))
            c.execute("UPDATE outbox SET status='failed',last_error_code='SENDER_DISCONNECTED',version=version+1 WHERE request_id=? AND kind='customer_received'",(ident,))
        staff.goto('/admin/requests/'+ident)
        expect(staff.get_by_text(re.compile('failed|needs attention',re.I)).first).to_be_visible()
        out=read(staff,'/admin/outbox?requestId='+ident)['body']['data']['items']
        failed=next(x for x in out if x['kind']=='customer_received')
        assert failed['status']=='failed' and not failed['canRetry']
        page.reload();expect(page.get_by_text(data['reference'],exact=False).first).to_be_visible()
    finally:staff_ctx.close()

def test_dundalk_no_photos_and_location_switch_preserves_input(page):
    submit=fill(page)
    page.locator('input[name="location"][value="dundalk"]').check()
    expect(page.get_by_label('Describe the item and the problem')).to_have_value(re.compile('Synthetic test'))
    expect(page.locator('#dundalk-panel')).to_be_visible()
    expect(page.locator('#dundalk-panel a[href="sms:+14433863800"]')).to_be_visible()
    expect(submit).to_contain_text('Dundalk')
    submit.click();data=receipt(page)
    assert data['location']=='dundalk' and data['appointmentConfirmed'] is False
    expect(page.get_by_text(re.compile('not an appointment')).first).to_be_visible()

def test_validation_phone_date_focus_and_retained_photo(page):
    submit=fill(page);attach(page,1)
    page.get_by_label('Your name',exact=True).fill('')
    page.locator('input[name="preferred"][value="text"]').check();submit.click()
    expect(page.locator('[aria-invalid="true"]').first).to_be_focused()
    expect(page.get_by_label('Describe the item and the problem')).to_have_value(re.compile('Synthetic test'))
    expect(page.locator('.photo-list li')).to_have_count(1)
    page.get_by_label('Your name',exact=True).fill('Synthetic Browser')
    page.get_by_label('Phone',exact=False).fill('2025550123')
    page.locator('input[name="neededBy"]').fill('2020-01-01');submit.click()
    expect(page.locator('input[name="neededBy"]')).to_have_attribute('aria-invalid','true')
    today=datetime.now(ZoneInfo('America/New_York')).date().isoformat();page.locator('input[name="neededBy"]').fill(today)
    expect(page.locator('.field-warning')).to_be_visible();submit.click();data=receipt(page)
    assert data['warnings'][0]['code']=='TIMING_NOT_CONFIRMED'

def test_bad_oversize_sixth_photo_and_real_heic(page):
    fill(page)
    page.locator('#photo-input').set_input_files([dict(name='wrong.pdf',mimeType='application/pdf',buffer=b'%PDF-test'),dict(name='huge.jpg',mimeType='image/jpeg',buffer=b'x'*10485761)])
    expect(page.get_by_text(re.compile('file type can')).first).to_be_visible()
    expect(page.get_by_text(re.compile('up to 10 MB each')).last).to_be_visible()
    page.locator('#photo-input').set_input_files('/opt/test-fixtures/phone-12mp.heic')
    page.wait_for_function("""()=>JSON.parse(sessionStorage.getItem('clarke.intake')||'null')?.data?.photos?.some(p=>p.state==='ready')""",timeout=40000)
    page.locator('#photo-input').set_input_files([photo(str(i)+'.jpg') for i in range(5)])
    expect(page.locator('#photo-input')).to_be_disabled()
    expect(page.get_by_text(re.compile('not added; remove one')).first).to_be_visible()
    # Inspect only this candidate's generated images, not a mock conversion result.
    with seed_sessions.database() as c:
        rows=list(c.execute("SELECT * FROM photos WHERE state='ready' AND bytes>100000 ORDER BY created_at DESC LIMIT 1"))
        assert rows
        with Image.open(Path('/data/uploads')/rows[0]['sanitized_key']) as image:assert not image.getexif() and image.width<=2048

def test_offline_failure_refresh_deep_link_and_back_keep_draft(page,context):
    submit=fill(page);attach(page,1)
    page.reload();expect(page.get_by_label('Your name',exact=True)).to_have_value('Synthetic Browser Customer')
    expect(page.locator('.photo-list li')).to_have_count(1)
    page.goto('/');page.go_back();expect(page.get_by_label('Your name',exact=True)).to_have_value('Synthetic Browser Customer')
    context.set_offline(True);page.locator('.request-form button[type="submit"]').click()
    expect(page.get_by_text(re.compile('offline|connection|reach the shop')).first).to_be_visible()
    expect(page.get_by_label('Your name',exact=True)).to_have_value('Synthetic Browser Customer')
    context.set_offline(False);page.locator('.request-form button[type="submit"]').click();receipt(page)

def test_double_submit_one_record(page):
    submit=fill(page);submit.evaluate('(el)=>{el.click();el.click();}');data=receipt(page)
    with seed_sessions.database() as c:
        assert c.execute('SELECT count(*) FROM requests WHERE contact_name=?',('Synthetic Browser Customer',)).fetchone()[0]>=1
        raw=page.evaluate("JSON.parse(sessionStorage.getItem('clarke.receipt')).data.statusUrl")
        secret=Path('/data/secret.key').read_bytes().strip()
        import hashlib,hmac
        digest=hmac.new(secret,('status\0'+raw.split('#token=')[1]).encode(),hashlib.sha256).hexdigest()
        assert c.execute('SELECT count(*) FROM requests WHERE status_token_hash=?',(digest,)).fetchone()[0]==1

def test_pause_and_closed_confirmation(page,browser):
    staff_ctx,staff,_=staff_page(browser)
    try:
        s=read(staff,'/admin/settings')['body']['data']
        assert mutate(staff,'/admin/settings',{'expectedVersion':s['version'],'intakeAccepting':False,'intakePauseMessage':'Call the shop while requests are paused.'},'PATCH')['status']==200
        page.goto('/repair-request');expect(page.locator('.request-form')).to_have_count(0)
        expect(page.locator('a[href="tel:+14108368316"]').first).to_be_visible()
        s=read(staff,'/admin/settings')['body']['data'];mutate(staff,'/admin/settings',{'expectedVersion':s['version'],'intakeAccepting':True},'PATCH')
        hours=read(staff,'/admin/hours')['body']['data'];mutate(staff,'/admin/hours',{'expectedVersion':hours['version'],'days':[None]*7},'PUT')
        fill(page).click();data=receipt(page);assert 'closed' in data['closureMessage'].lower() and data['nextOpensAt'] is None
        mutate(staff,'/admin/hours',{'expectedVersion':hours['version']+1,'days':hours['days']},'PUT')
    finally:staff_ctx.close()

@pytest.mark.parametrize('choice',['accept','decline','request_call'])
def test_staff_estimate_customer_response_ready_and_privacy(page,browser,choice):
    fill(page,'dundalk').click();data=receipt(page)
    staff_ctx,staff,_=staff_page(browser,width=page.viewport_size['width'])
    try:
        ident=find_request(staff,data['reference']);ui_offer(staff,ident)
        out=read(staff,'/admin/outbox?requestId='+ident)['body']['data']['items'];estimate=next(x for x in out if x['kind']=='customer_estimate')
        mail=read(staff,'/admin/outbox/'+estimate['id'])['body']['data'];assert '$12.34' in mail['bodyText'] and 'final price confirmed' in mail['bodyText']
        page.goto(data['statusUrl']);expect(page.get_by_role('heading',name='Your estimate',exact=True)).to_be_visible()
        if choice=='accept':page.get_by_role('button',name=re.compile('Accept,')).click()
        elif choice=='decline':
            page.get_by_role('button',name='No thanks',exact=True).click();page.get_by_role('button',name='Yes, close my request',exact=True).click()
        else:
            page.get_by_role('button',name='Please call me',exact=True).click();page.get_by_label('Phone number to call').fill('2025550123');page.get_by_role('button',name='Request a call',exact=True).click()
        expect(page.get_by_text(re.compile('You replied')).first).to_be_visible()
        page.reload();expect(page.get_by_role('button',name='Please call me',exact=True)).to_have_count(0)
        detail=read(staff,'/admin/requests/'+ident)['body']['data']
        assert detail['offer']['response']['choice']==choice
        if choice=='accept':
            local=datetime.now(ZoneInfo('America/New_York'))
            closure=dict(locations=['dundalk'],message='Synthetic pickup closure: call before visiting.',reopenText=None,startsAt=(local-timedelta(minutes=1)).isoformat(timespec='seconds'),endsAt=(local+timedelta(minutes=15)).isoformat(timespec='seconds'))
            assert mutate(staff,'/admin/notices',closure)['status']==201
            staff.reload();staff.get_by_label('Add an internal note').fill('Private note must never reach the customer.');staff.get_by_role('button',name='Add note',exact=True).click()
            staff.get_by_label('Status',exact=True).select_option('ready');staff.get_by_label('Pickup location',exact=True).select_option('dundalk');staff.get_by_role('button',name='Update status',exact=True).click()
            expect(staff.get_by_text(re.compile('Status changed to')).first).to_be_visible()
            page.reload();expect(page.locator('#status-title')).to_contain_text('Ready for pickup')
            assert 'Private note' not in page.locator('body').inner_text()
            expect(page.locator('a[href="sms:+14433863800"]').first).to_be_visible()
            expect(page.get_by_text(closure['message'],exact=True).first).to_be_visible()
            out=read(staff,'/admin/outbox?requestId='+ident)['body']['data']['items']
            ready=next(x for x in out if x['kind']=='customer_ready')
            assert closure['message'] in read(staff,'/admin/outbox/'+ready['id'])['body']['data']['bodyText']
    finally:staff_ctx.close()

def test_needs_visit_and_not_repairable(page,browser):
    page.goto('/');data,_=api_request(page);staff_ctx,staff,_=staff_page(browser)
    try:
        ident=find_request(staff,data['reference']);ui_offer(staff,ident,True)
        page.goto(data['statusUrl']);expect(page.locator('#status-title')).to_have_text('Please bring it in')
        staff.get_by_label('Status',exact=True).select_option('not_repairable')
        staff.locator('textarea[name="customerMessage"]').fill('The synthetic material cannot support this repair.')
        staff.get_by_role('button',name='Update status',exact=True).click();expect(staff.get_by_text(re.compile('Status changed to')).first).to_be_visible()
        page.reload();expect(page.locator('#status-title')).to_contain_text('repair this')
        expect(page.get_by_role('button',name='Please call me',exact=True)).to_have_count(0)
    finally:staff_ctx.close()

def test_lookup_mismatch_phone_last4_expired_and_invalid_link(page,browser):
    page.goto('/');data,p=api_request(page,phone='+12025550123')
    page.goto('/repair-status');page.locator('input[name="reference"]').fill(data['reference']);page.locator('input[name="value"]').fill('wrong@example.test')
    page.locator('[data-lookup] button[type="submit"]').click()
    expect(page.get_by_text('This request is unavailable. Check your details or call the shop.',exact=True)).to_be_visible()
    page.locator('input[name="value"]').fill(p['contact']['email']);page.locator('[data-lookup] button[type="submit"]').click();expect(page.locator('#status-title')).to_have_text('Received')
    page.get_by_role('button',name='Forget this link in this tab').click()
    page.locator('input[name="reference"]').fill(data['reference']);page.locator('input[name="verifyType"][value="phone_last4"]').check();page.locator('input[name="value"]').fill('0123')
    page.locator('[data-lookup] button[type="submit"]').click();expect(page.locator('#status-title')).to_have_text('Received')
    with seed_sessions.database() as c:c.execute("UPDATE requests SET status='picked_up',closed_at=? WHERE contact_name='Synthetic Browser Setup'",(int(time.time()*1000)-91*86400000,))
    page.reload();expect(page.locator('input[name="reference"]')).to_be_visible()
    page.goto('/repair-status#token='+'invalid'*8);expect(page.locator('input[name="reference"]')).to_be_visible()

def test_viewer_inbox_filters_estimates_management_denied(page,context):
    page.goto('/');data,_=api_request(page)
    identity=seed_sessions.seed('viewer');context.add_cookies([identity['cookie']]);page.goto('/admin/requests')
    page.get_by_label('Search',exact=True).fill(data['reference']);page.get_by_role('button',name='Search',exact=True).click()
    expect(page.locator('.request-row')).to_have_count(1);page.locator('.request-row').click()
    expect(page.get_by_label('Amount in dollars',exact=True)).to_be_visible()
    for path in ('settings','locations','notices','team','emails','audit'):
        response=page.goto('/admin/'+path);assert response.status==403
    page.goto('/admin/requests');page.get_by_label('Search',exact=True).fill('unmatched-synthetic-value');page.get_by_role('button',name='Search',exact=True).click()
    expect(page.get_by_text('No matching requests',exact=True)).to_be_visible()

def test_conflict_and_expired_session_preserve_staff_draft(page,context,browser,admin):
    page.goto('/admin/requests');data,_=api_request(page);ident=find_request(page,data['reference']);page.goto('/admin/requests/'+ident)
    page.get_by_label('Amount in dollars',exact=True).fill('12.34');page.get_by_label('What the estimate covers').fill('Preserve this synthetic draft during conflicts.')
    other_ctx,other,_=staff_page(browser)
    try:
        assert mutate(other,'/admin/requests/'+ident,{'expectedVersion':1,'status':'reviewing'},'PATCH')['status']==200
        page.get_by_role('button',name='Send estimate',exact=True).click();page.get_by_role('dialog').get_by_role('button',name='Send estimate',exact=True).click()
        expect(page.get_by_text(re.compile('Updated by someone else')).first).to_be_visible()
        expect(page.get_by_label('What the estimate covers')).to_have_value('Preserve this synthetic draft during conflicts.')
        page.reload();expect(page.get_by_label('What the estimate covers')).to_have_value('Preserve this synthetic draft during conflicts.')
        seed_sessions.expire(admin['memberId']);page.get_by_role('button',name='Send estimate',exact=True).click();page.get_by_role('dialog').get_by_role('button',name='Send estimate',exact=True).click()
        expect(page.get_by_text(re.compile('session.*ended|session.*expired|Sign in again')).first).to_be_visible()
        stored=page.evaluate('Object.entries(sessionStorage).filter(([k])=>k.startsWith("clarke.staff."))')
        assert 'Preserve this synthetic draft' in json.dumps(stored)
    finally:other_ctx.close()

def test_locations_notice_every_surface_fallback_links_and_containment(page,browser):
    page.goto('/');staff_ctx,staff,_=staff_page(browser)
    try:
        local=datetime.now(ZoneInfo('America/New_York'));notice=dict(locations=['bel_air','dundalk'],message='Synthetic closure visible for this test.',reopenText='Call before visiting.',startsAt=(local-timedelta(minutes=1)).isoformat(timespec='seconds'),endsAt=(local+timedelta(minutes=30)).isoformat(timespec='seconds'))
        assert mutate(staff,'/admin/notices',notice)['status']==201
        for path in ('/','/repair-request'):
            page.goto(path);expect(page.get_by_text(notice['message'],exact=True).first).to_be_visible()
        page.route('**/api/v1/locations',lambda route:route.abort())
        page.goto('/');expect(page.get_by_text(re.compile('Call before visiting',re.I)).first).to_be_visible()
        page.unroute('**/api/v1/locations')
        page.goto('/');text=page.locator('body').inner_text();assert '410-284-2458' not in text
        for href in ('tel:+14108368316','tel:+14433863800','sms:+14433863800'):
            assert page.locator(f'a[href="{href}"]').count()>0
        assert page.locator('a[href*="facebook.com/clarkesexpressshoerepair"]').count()>0
        assert page.locator('a[href*="instagram.com/clarke_the_shoe_doc"]').count()>0
        assert page.locator('a[href*="google.com/maps"]').count()>=2
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        fill(page);page.evaluate("document.documentElement.style.fontSize='200%'")
        assert page.evaluate('''()=>[...document.querySelectorAll('.form-card input:not([type=radio]):not([type=checkbox]):not([type=file]),.form-card textarea,.form-card select')].filter(x=>x.getClientRects().length&&!x.closest('.honeypot')).every(x=>{const a=x.getBoundingClientRect(),b=x.closest('.form-card').getBoundingClientRect();return a.left>=b.left-1&&a.right<=b.right+1})''')
    finally:staff_ctx.close()
