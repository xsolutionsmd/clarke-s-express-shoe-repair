from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import re
from playwright.sync_api import expect
from test_flows import staff_page
from conftest import mutate


def test_public_notice_expires_without_refresh(page,browser):
    staff_ctx,staff,_=staff_page(browser)
    try:
        local=datetime.now(ZoneInfo('America/New_York'))
        notice=dict(locations=['bel_air'],message='Synthetic short closure expires automatically.',reopenText=None,startsAt=(local-timedelta(seconds=5)).isoformat(timespec='seconds'),endsAt=(local+timedelta(seconds=14)).isoformat(timespec='seconds'))
        assert mutate(staff,'/admin/notices',notice)['status']==201
        page.goto('/')
        expect(page.get_by_text(notice['message'],exact=True).first).to_be_visible()
        expect(page.get_by_text(notice['message'],exact=True)).to_have_count(0,timeout=25000)
    finally:staff_ctx.close()


def test_notice_editor_invalid_time_and_saved_public_banner(page,admin):
    page.goto('/admin/notices')
    expect(page.get_by_role('heading',name='Notices',exact=True)).to_be_visible()
    # Editors can be inline or opened with the labelled creation action.
    if page.locator('input[type="datetime-local"]').count()==0:
        page.get_by_role('button',name=re.compile('(new|add|create).*notice',re.I)).first.click()
    page.locator('input[value="bel_air"]').first.check()
    page.locator('textarea').first.fill('Synthetic notice editor validation.')
    start=page.locator('input[type="datetime-local"]').nth(0)
    end=page.locator('input[type="datetime-local"]').nth(1)
    local=datetime.now(ZoneInfo('America/New_York')).replace(second=0,microsecond=0)
    start.fill((local-timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M'))
    end.fill((local-timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M'))
    submit=page.locator('form').filter(has=start).locator('button[type="submit"]')
    submit.click()
    expect(page.get_by_text(re.compile('after.*start|after.*begin|end.*after',re.I)).first).to_be_visible()
    end.fill((local+timedelta(minutes=20)).strftime('%Y-%m-%dT%H:%M'))
    submit.click()
    dialog=page.get_by_role('dialog')
    if dialog.count():
        dialog.get_by_role('button',name=re.compile('post|save|publish|create',re.I)).last.click()
    expect(page.get_by_text('Synthetic notice editor validation.',exact=True).first).to_be_visible()
    page.goto('/')
    expect(page.get_by_text('Synthetic notice editor validation.',exact=True).first).to_be_visible()


def test_main_routes_no_browser_errors_or_missing_resources(page,admin,context):
    errors=[];failures=[]
    page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' else None)
    page.on('response',lambda response:failures.append((response.status,response.url.split('?')[0])) if response.status>=400 else None)
    page.on('requestfailed',lambda req:failures.append(('network',req.url.split('?')[0])))
    if page.viewport_size['width']==375:
        cdp=context.new_cdp_session(page)
        cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
        cdp.send('Network.enable')
        cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':40,'downloadThroughput':1500000/8,'uploadThroughput':750000/8})
    for path in ('/','/repair-request','/repair-status','/admin/requests','/admin/requests/new','/admin/locations','/admin/notices','/admin/settings','/admin/team','/admin/emails','/admin/audit'):
        response=page.goto(path,wait_until='networkidle')
        assert response.status==200,(path,response.status)
        expect(page.locator('h1').first).to_be_visible()
        assert page.evaluate('performance.getEntriesByType("navigation")[0].domContentLoadedEventEnd')<10000,path
        assert not errors,(path,errors)
        assert not failures,(path,failures)
