"""Intake thresholds through real request handlers, with independent drafts."""
import uuid

import pytest
from clarke import core, db
from conftest import headers, repair_body


@pytest.mark.parametrize('bucket,capacity', [('ip', 10), ('email', 3), ('phone', 3)])
def test_intake_rate_limit_distinct_drafts_and_unrelated_request(app, client, bucket, capacity):
    seen = set()

    def attempt(number, unrelated=False):
        h = headers(client)
        # Draft creation has its own 10/hour IP limit. Use independent creation
        # addresses so the assertion below actually reaches the intake limiter.
        draft = client.post('/api/v1/drafts', json={}, headers=h,
                            environ_overrides={'REMOTE_ADDR': f'192.0.2.{number + 1}'})
        assert draft.status_code == 201, draft.json
        d = draft.json['data']
        assert d['draftId'] not in seen
        seen.add(d['draftId'])
        p = repair_body(d['draftId'])
        if bucket == 'email' and not unrelated:
            p['contact']['email'] = 'Limited@Example.Test' if number % 2 else 'limited@example.test'
        if bucket == 'phone' and not unrelated:
            p['contact']['phone'] = '+12025550123'
        ip = '198.51.100.10' if bucket == 'ip' and not unrelated else f'203.0.113.{number + 1}'
        h.update({'X-Draft-Token': d['draftToken'], 'Idempotency-Key': str(uuid.uuid4()),
                  'X-Forwarded-For': f'192.0.2.{number + 100}'})
        response = client.post('/api/v1/requests', json=p, headers=h,
                               environ_overrides={'REMOTE_ADDR': ip})
        return response, d

    for number in range(capacity):
        response, _ = attempt(number)
        assert response.status_code == 201, response.json

    with app.app_context(), db.connect() as c:
        counts = tuple(c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                       for table in ('requests', 'request_events', 'outbox'))
        identity = {'ip': '198.51.100.10', 'email': 'limited@example.test', 'phone': '+12025550123'}[bucket]
        key = core.digest('limit', 'request-' + bucket + '\0' + identity)
        assert c.execute('SELECT tokens FROM rate_limits WHERE bucket_key=?', (key,)).fetchone()[0] < 1

    # Two new drafts also rule out accidentally exercising submission replay.
    for number in (capacity, capacity + 1):
        response, d = attempt(number)
        assert response.status_code == 429, response.json
        assert response.json['error']['code'] == 'RATE_LIMITED'
        assert int(response.headers['Retry-After']) > 0
        with app.app_context(), db.connect() as c:
            assert tuple(c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                         for table in ('requests', 'request_events', 'outbox')) == counts
            row = c.execute('SELECT state,request_id FROM drafts WHERE id=?', (d['draftId'],)).fetchone()
            assert tuple(row) == ('active', None)

    response, _ = attempt(capacity + 2, unrelated=True)
    assert response.status_code == 201, response.json
    with app.app_context(), db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == capacity + 1
