import hashlib
import json
import secrets
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
import test_system as system
from scripts.adapter_push import signed_headers
s = system.s


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        system.SystemTests.setUp(self)
        with s.db() as c:
            for table in ('connectors', 'connector_batches', 'connector_events', 'connector_nonces'):
                c.execute('DELETE FROM '+table)

    def connector(self, **overrides):
        response = self.client.post('/api/integrations', json={
            'name': '验收适配器', 'dataset': 'actual', 'properties': ['bhl'],
            'kinds': ['customer', 'order', 'payment', 'fulfillment'], 'expires_days': 1, **overrides})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def batch(self, **overrides):
        return {'batch_id': 'batch-1', 'dataset': 'actual', 'property_id': 'bhl', 'kind': 'customer',
                'rows': [{'external_id': 'ADAPTER-C', 'code': 'ADAPTER-C', 'day': '2026-11-06', 'owner': '客服', 'status': 'new'}], **overrides}

    def push(self, key, batch, **header_overrides):
        raw = json.dumps(batch, ensure_ascii=False, separators=(',', ':')).encode()
        headers = {**signed_headers(key, raw), **header_overrides}
        return self.client.post('/api/integrations/ingest', content=raw, headers=headers)

    def test_batch_idempotency_and_changed_payload_rejection(self):
        key = self.connector()['token']; batch = self.batch()
        first = self.push(key, batch); self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), {'inserted': 1, 'skipped': 0, 'replayed': False})
        self.assertTrue(self.push(key, batch).json()['replayed'])
        self.assertEqual(self.push(key, {**batch, 'batch_id': 'new-batch'}).json()['skipped'], 1)
        changed = self.batch(rows=[{**batch['rows'][0], 'owner': '变更'}])
        self.assertEqual(self.push(key, changed).status_code, 409)
        with s.db() as c:
            self.assertEqual(len(s.records(c, 'actual', 'customer')), 1)
            self.assertNotIn(key, '\n'.join(c.iterdump()))
        listing = self.client.get('/api/integrations').json()
        self.assertNotIn('token_hash', listing['connectors'][0]); self.assertFalse(listing['native_platform_connected'])

    def test_signature_clock_nonce_revocation_and_expiry(self):
        conn = self.connector(); key = conn['token']; raw = json.dumps(self.batch()).encode()
        headers = signed_headers(key, raw)
        self.assertEqual(self.client.post('/api/integrations/ingest', content=raw+b' ', headers=headers).status_code, 401)
        self.assertEqual(self.push(key, self.batch(), **{'X-Hotel-Signature': 'wrong'}).status_code, 401)
        old = signed_headers(key, raw, timestamp=int(time.time())-301)
        self.assertEqual(self.client.post('/api/integrations/ingest', content=raw, headers=old).status_code, 401)
        self.assertEqual(self.client.post('/api/integrations/ingest', content=raw, headers=headers).status_code, 200)
        self.assertEqual(self.client.post('/api/integrations/ingest', content=raw, headers=headers).status_code, 409)
        self.assertEqual(self.client.post(f'/api/integrations/{conn["id"]}/revoke').status_code, 200)
        self.assertEqual(self.push(key, self.batch()).status_code, 401)
        fresh = self.connector()
        with s.db() as c:c.execute('UPDATE connectors SET expires_at=? WHERE id=?', ('2020-01-01', fresh['id']))
        self.assertEqual(self.push(fresh['token'], self.batch()).status_code, 401)

    def test_scope_and_admin_only_management(self):
        key = self.connector(kinds=['customer'])['token']
        for change in ({'dataset': 'demo'}, {'property_id': 'jtw'}, {'kind': 'cost'}):
            self.assertEqual(self.push(key, self.batch(**change)).status_code, 403)
        self.assertEqual(self.client.post('/api/integrations', json={'name': '无范围', 'dataset': 'actual', 'properties': ['*'], 'kinds': ['order']}).status_code, 422)
        client = TestClient(s.app)
        self.assertEqual(client.get('/api/integrations').status_code, 401)
        client.post('/api/login', json={'demo': True})
        self.assertEqual(client.get('/api/integrations').status_code, 403)
        self.assertEqual(client.post('/api/integrations', json={}).status_code, 403)
        password = secrets.token_urlsafe(20)
        self.client.post('/api/users', json={'username': 'adapter-manager', 'password': password, 'role': 'manager', 'properties': ['bhl']})
        client.post('/api/login', json={'username': 'adapter-manager', 'password': password})
        self.assertEqual(client.get('/api/integrations').status_code, 403)
        self.assertEqual(client.post('/api/integrations/1/revoke').status_code, 403)

    def test_failed_batch_rolls_back_and_can_be_corrected(self):
        key = self.connector()['token']; rows = self.batch()['rows']
        bad = self.batch(rows=rows+[{**rows[0], 'external_id': 'BAD', 'code': 'BAD', 'day': 'bad-date'}])
        response = self.push(key, bad); self.assertEqual(response.status_code, 422, response.text)
        with s.db() as c:
            self.assertEqual(s.records(c, 'actual', 'customer'), [])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM connector_batches').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT status FROM connector_events').fetchone()[0], 422)
        self.assertEqual(self.push(key, self.batch()).status_code, 200)
        self.assertEqual(self.push(key, self.batch(batch_id='unknown', rows=[{**rows[0], 'unmapped': 1}])).status_code, 422)
        for raw in (b'[]', b'{bad'):
            self.assertEqual(self.client.post('/api/integrations/ingest', content=raw, headers=signed_headers(key, raw)).status_code, 400)

    def test_concurrent_same_batch_is_inserted_once(self):
        key = self.connector()['token']; raw = json.dumps(self.batch()).encode()
        def send(_):
            with TestClient(s.app) as client:
                response = client.post('/api/integrations/ingest', content=raw, headers=signed_headers(key, raw))
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()['replayed']
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(send, range(2))), [False, True])
        with s.db() as c:self.assertEqual(len(s.records(c, 'actual', 'customer')), 1)

    def test_signed_orders_refunds_and_dashboard_agree(self):
        key = self.connector()['token']
        events = [
            ('order', dict(external_id='A-O', order_no='A-O', order_date='2026-11-01', checkin='2026-11-02', checkout='2026-11-03', kind='stay', status='completed', booking_amount=1000, channel='unknown', traffic='unknown')),
            ('payment', dict(external_id='A-P', order_no='A-O', day='2026-11-01', type='collection', destination='bank', amount=1000, revenue_reversal=0)),
            ('fulfillment', dict(external_id='A-F', order_no='A-O', day='2026-11-02', business='room', amount=1000, room_nights=1, included=False, guest_type='not_applicable')),
            ('payment', dict(external_id='A-R', order_no='A-O', day='2026-11-03', type='refund', destination='bank', amount=100, revenue_reversal=100, fulfillment_ref='A-F'))]
        for index, (kind, row) in enumerate(events):
            batch = self.batch(batch_id='event-'+str(index), kind=kind, rows=[row])
            response = self.push(key, batch); self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(self.push(key, batch).json()['replayed'])
        report = self.client.get('/api/dashboard?dataset=actual&property_id=bhl&start=2026-11-01&end=2026-11-04&asof=2026-11-05').json()
        self.assertEqual(report['metrics']['revenue'], 900)
        self.assertEqual(report['metrics']['paid_net'], 900)
        self.assertEqual(report['metrics']['room_nights'], 1)
        self.assertEqual(sum(o['fulfilled_revenue'] for o in report['orders']), 900)
