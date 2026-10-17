"""Customer wording and navigation regressions from Sol/parent round 4."""
import uuid
import pytest
from conftest import submit, identify, staff
from clarke import core, db, mail

LABELS = {'shoes':'Shoes','boots':'Boots','handbag_purse':'Handbag or purse','belt_strap':'Belt or strap','leather_garment':'Leather jacket or garment','luggage':'Luggage','baseball_glove':'Baseball glove','other_leather':'Other leather item','keys':'Keys (ask us)'}

@pytest.mark.parametrize('item,label', LABELS.items())
def test_notification_item_labels_for_customer_and_staff(app, client, item, label):
    receipt, _, _ = submit(client, itemType=item)
    ident = identify(app, receipt)
    with app.app_context(), db.connect() as c:
        rows = c.execute('SELECT * FROM outbox WHERE request_id=?', (ident,)).fetchall()
        assert {r['kind'] for r in rows} == {'customer_received', 'staff_new_request'}
        for row in rows:
            content = core.decrypt(row['body_cipher'])
            assert content['bodyText'].split('\n\n')[2] == label
            assert label in content['bodyHtml']

@pytest.mark.parametrize('location', ['bel_air', 'dundalk'])
def test_ready_status_and_mail_use_pickup_route(app, client, location):
    receipt, _, _ = submit(client, location=location)
    ident = identify(app, receipt)
    admin, headers, _ = staff(app)
    result = admin.patch('/api/v1/admin/requests/'+ident, json={'expectedVersion':1,'status':'ready','pickupLocation':location}, headers=headers)
    assert result.status_code == 200
    token = receipt['statusUrl'].split('#token=')[1]
    status = client.get('/api/v1/status', headers={'Authorization':'Bearer '+token}).json['data']
    with app.app_context(), db.connect() as c:
        queued = c.execute("SELECT * FROM outbox WHERE request_id=? AND kind='customer_ready'", (ident,)).fetchone()
        content = core.decrypt(queued['body_cipher'])
    for text in (status['nextAction'], content['bodyText'], content['bodyHtml']):
        assert 'Bring your item' not in text
        assert ('Collect your item at 23 South Main St. (REAR), Burns Alley, Bel Air.' if location == 'bel_air' else 'Call or text 443-386-3800') in text
    if location == 'bel_air':
        assert 'Bring your item' in mail.route_message(location)


def test_navigation_404_is_html_and_api_assets_keep_json(app, client, monkeypatch, tmp_path):
    import server
    (tmp_path/'dist').mkdir()
    (tmp_path/'dist'/'not-found.html').write_text('<h1>Page not found</h1><a href="/">Home</a>')
    monkeypatch.setattr(server, 'BASE', tmp_path)
    for path in ('/not-a-real-page', '/admin/not-a-real-page'):
        result = client.get(path, headers={'Accept':'text/html'})
        assert result.status_code == 404 and result.mimetype == 'text/html'
        assert b'Page not found' in result.data
        assert client.get(path, headers={'Accept':'application/json'}).is_json
    for path in ('/api/v1/not-real', '/oauth/not-real', '/uploads/not-real', '/data/not-real', '/missing.js'):
        result = client.get(path, headers={'Accept':'text/html'})
        assert result.status_code == 404 and result.is_json


def test_unrelated_settings_patch_preserves_pending_policy(app):
    admin, headers, _ = staff(app)
    def patch(body):
        current = admin.get('/api/v1/admin/settings').json['data']
        return admin.patch('/api/v1/admin/settings', json={'expectedVersion':current['version']} | body, headers=headers | {'Idempotency-Key':str(uuid.uuid4())})
    assert patch({'photoRetentionDays':90,'closedLinkDays':60,'confirmRetentionReduction':True}).status_code == 200
    pending = admin.get('/api/v1/admin/settings').json['data']['pendingRetention']
    assert patch({'responseExpectation':'Staff-only planning note.'}).status_code == 200
    assert admin.get('/api/v1/admin/settings').json['data']['pendingRetention'] == pending
    assert patch({'photoRetentionDays':180,'closedLinkDays':90}).status_code == 200
    assert admin.get('/api/v1/admin/settings').json['data']['pendingRetention'] is None
