"""Four-gap acceptance follow-up; real isolated HTTP, no provider delivery."""
import re
from urllib.parse import quote

import pytest
from playwright.sync_api import expect
import seed_sessions
from conftest import mutate, read
from test_flows import fill, attach, receipt, api_request, find_request, staff_page


@pytest.mark.parametrize('context', [375], indirect=True, ids=['phone'])
def test_real_intake_503_retains_photo_fields_fallback_and_retry(page):
    submit = fill(page)
    attach(page, 1)
    before = page.evaluate('JSON.parse(sessionStorage.getItem("clarke.intake")).data')
    responses = []
    page.on('response', lambda r: responses.append(r) if r.url.endswith('/api/v1/requests') and r.request.method == 'POST' else None)
    # Hold a real competing SQLite writer until the application's busy timeout.
    # No browser interception or runtime fault-injection route is involved.
    with seed_sessions.database() as locked:
        count = locked.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
        locked.execute('BEGIN IMMEDIATE')
        with page.expect_response(lambda r: r.url.endswith('/api/v1/requests') and r.request.method == 'POST', timeout=15000) as failed:
            submit.click()
        assert failed.value.status == 503
        assert failed.value.json()['error']['code'] == 'DATABASE_BUSY'
        assert locked.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == count
    alert = page.locator('.request-form [role="alert"]')
    expect(alert).to_be_visible()
    expect(alert.locator('a[href="tel:+14108368316"]')).to_be_visible()
    expect(alert.locator('a[href="tel:+14433863800"]')).to_be_visible()
    expect(page.get_by_label('Your name', exact=True)).to_have_value(before['fields']['name'])
    expect(page.get_by_label('Email', exact=True)).to_have_value(before['fields']['email'])
    expect(page.get_by_label('Describe the item and the problem')).to_have_value(before['fields']['description'])
    expect(page.locator('input[name="location"][value="bel_air"]')).to_be_checked()
    expect(page.locator('input[name="itemType"][value="boots"]')).to_be_checked()
    expect(page.locator('input[name="workTypes"][value="soles_heels"]')).to_be_checked()
    expect(page.locator('.photo-list li')).to_have_count(1)
    expect(page.locator('.photo-list li')).to_contain_text('shoe-0.jpg')
    expect(page.locator('.photo-list li')).to_contain_text('Ready,')
    saved = page.evaluate('JSON.parse(sessionStorage.getItem("clarke.intake")).data')
    assert saved['fields'] == before['fields'] and saved['photos'] == before['photos']
    alert.get_by_role('button', name='Try again', exact=True).click()
    receipt(page)
    assert [r.status for r in responses] == [503, 201]
    assert responses[0].request.headers['idempotency-key'] == responses[1].request.headers['idempotency-key']
    with seed_sessions.database() as c:
        assert c.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == count + 1
        draft = c.execute('SELECT state,request_id FROM drafts WHERE id=?', (before['draft']['id'],)).fetchone()
        assert draft['state'] == 'submitted'
        photos = c.execute('SELECT id FROM photos WHERE request_id=?', (draft['request_id'],)).fetchall()
        assert [r['id'] for r in photos] == [before['photos'][0]['photoId']]
        assert c.execute('SELECT COUNT(*) FROM request_events WHERE request_id=? AND type=?', (draft['request_id'], 'received')).fetchone()[0] == 1
        assert not c.execute("SELECT 1 FROM outbox WHERE status IN ('sent','pending','retry_wait')").fetchone()


@pytest.mark.parametrize('context', [1440], indirect=True, ids=['desktop'])
def test_same_member_session_return_retains_estimate_and_stale_guard(page, context, browser, admin):
    page.goto('/admin/requests')
    data, _ = api_request(page)
    ident = find_request(page, data['reference'])
    path = '/admin/requests/' + ident
    page.goto(path)
    scope = 'Restore this synthetic sole estimate after the same member signs in.'
    page.get_by_label('Amount in dollars', exact=True).fill('12.34')
    page.get_by_label('What the estimate covers').fill(scope)

    def saved():
        return page.evaluate('([member,id]) => JSON.parse(sessionStorage.getItem("clarke.staff."+member)).data["req:"+id+":offer"]', [admin['memberId'], ident])

    original = saved()
    seed_sessions.expire(admin['memberId'])
    with page.expect_response(lambda r: r.url.endswith('/offers') and r.request.method == 'POST') as expired:
        page.get_by_role('button', name='Send estimate', exact=True).click()
        page.get_by_role('dialog').get_by_role('button', name='Send estimate', exact=True).click()
    assert expired.value.status == 401
    expect(page.locator('.session-banner')).to_contain_text('Your session ended')
    with page.expect_response('**/api/v1/auth/google/start') as start:
        page.get_by_role('button', name='Sign in with Google', exact=True).click()
    assert start.value.status == 503  # no provider is configured in this isolated runtime
    return_to = start.value.request.post_data_json['returnTo']
    assert return_to == path

    other_context, other, _ = staff_page(browser)
    try:
        changed = mutate(other, '/admin/requests/' + ident,
                         {'expectedVersion': original['baseVersion'], 'status': 'reviewing'}, 'PATCH')
        assert changed['status'] == 200
        current_version = changed['body']['data']['version']
    finally:
        other_context.close()
    identity = seed_sessions.seed('admin', member_id=admin['memberId'])
    assert identity['memberId'] == admin['memberId']
    assert identity['cookie']['value'] != admin['cookie']['value']
    context.add_cookies([identity['cookie']])
    # The normal login page validates the signed session and follows returnTo.
    page.goto('/admin/login?returnTo=' + quote(return_to, safe=''))
    page.wait_for_url('**' + path)
    assert read(page, '/admin/session')['body']['data']['member']['id'] == admin['memberId']
    expect(page.get_by_label('Amount in dollars', exact=True)).to_have_value('12.34')
    expect(page.get_by_label('What the estimate covers')).to_have_value(scope)
    compare = page.get_by_role('region', name='Compare current values and your draft')
    expect(compare).to_be_visible()
    expect(compare).to_contain_text(scope)
    assert saved()['baseVersion'] == original['baseVersion'] < current_version
    writes = []
    page.on('request', lambda r: writes.append(r) if r.url.endswith('/offers') and r.method == 'POST' else None)
    page.get_by_role('button', name='Send estimate', exact=True).click()
    expect(compare).to_be_visible()
    expect(page.get_by_role('dialog')).to_have_count(0)
    assert not writes and not read(page, '/admin/requests/' + ident + '/offers')['body']['data']['items']
    compare.get_by_role('button', name='Reapply my draft', exact=True).click()
    assert saved()['baseVersion'] == current_version
    page.get_by_role('button', name='Send estimate', exact=True).click()
    expect(page.get_by_role('dialog')).to_be_visible()
    assert not writes
    with page.expect_response(lambda r: r.url.endswith('/offers') and r.request.method == 'POST') as sent:
        page.get_by_role('dialog').get_by_role('button', name='Send estimate', exact=True).click()
    assert sent.value.status == 201 and len(writes) == 1
    expect(page.get_by_text(re.compile('Estimate sent to the customer'))).to_be_visible()
    assert writes[0].post_data_json['expectedVersion'] == current_version
    with seed_sessions.database() as c:
        offers = c.execute('SELECT * FROM offers WHERE request_id=?', (ident,)).fetchall()
        assert len(offers) == 1
        assert (offers[0]['amount_min'], offers[0]['scope'], offers[0]['created_by']) == (1234, scope, admin['memberId'])
        assert c.execute('SELECT COUNT(*) FROM request_events WHERE related_offer_id=?', (offers[0]['id'],)).fetchone()[0] == 1
