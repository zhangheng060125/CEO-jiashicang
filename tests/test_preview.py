import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import test_system as system
s=system.s


class PreviewTests(unittest.TestCase):
 def setUp(self):system.SystemTests.setUp(self)
 put=system.SystemTests.put

 def test_public_entry_uses_only_demo_dates_without_writing(self):
  order=dict(order_no='ACTUAL',order_date='2026-10-31',checkin='2026-11-01',checkout='2026-11-02',kind='stay',status='completed',booking_amount=2000,channel='offline',traffic='organic')
  self.put('order','ACTUAL',order)
  self.put('fulfillment','ACTUAL-F',dict(order_no='ACTUAL',day='2026-11-01',business='room',amount=2000,room_nights=1,included=False,guest_type='not_applicable'))
  public=TestClient(s.app)
  with patch.dict(os.environ,{'HOTEL_ALLOW_DEMO':'1'}):
   self.assertFalse(public.get('/api/preview-info').json()['ready'])
   self.put('order','DEMO',{**order,'order_no':'DEMO','checkin':'2026-10-29','checkout':'2026-10-30'},dataset='demo')
   self.put('fulfillment','DEMO-F',dict(order_no='DEMO',day='2026-10-29',business='room',amount=1000,room_nights=1,included=False,guest_type='not_applicable'),dataset='demo')
   with s.db() as c:before=[tuple(r) for r in c.execute('SELECT * FROM records ORDER BY id')];sessions=c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
   info=public.get('/api/preview-info').json()
   self.assertEqual(info,{'enabled':True,'ready':True,'start':'2026-09-30','end':'2026-10-29','asof':'2026-10-29'})
   page=public.get('/preview');self.assertEqual(page.status_code,200);self.assertIn('preview-enter',page.text)
   self.assertEqual(public.get('/preview.js').status_code,200)
   self.assertEqual(public.get('/api/records/order?dataset=actual').status_code,401)
   with s.db() as c:
    self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM records ORDER BY id')],before)
    self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],sessions)

 def test_disabled_preview_hides_metadata_and_rejects_entry(self):
  public=TestClient(s.app)
  with patch.dict(os.environ,{'HOTEL_ALLOW_DEMO':'0'}):
   self.assertEqual(public.get('/api/preview-info').json(),{'enabled':False})
   self.assertEqual(public.post('/api/login',json={'demo':True}).status_code,403)
   self.assertEqual(public.get('/preview').status_code,200)

 def test_preview_session_cannot_switch_to_actual_or_manage_accounts(self):
  public=TestClient(s.app)
  with patch.dict(os.environ,{'HOTEL_ALLOW_DEMO':'1'}):
   self.assertEqual(public.post('/api/login',json={'demo':True}).status_code,200)
  self.assertTrue(public.get('/api/me').json()['demo'])
  self.assertEqual(public.get('/api/dashboard?dataset=actual').status_code,403)
  response=public.post('/api/records/customer',json={'dataset':'actual','property_id':'bhl','external_id':'PREVIEW-ESCAPE','data':dict(code='PREVIEW-ESCAPE',day=s.TODAY(),owner='test',status='new')})
  self.assertEqual(response.status_code,403)
  self.assertEqual(public.get('/api/users').status_code,403)
  self.assertEqual(public.get('/api/integrations').status_code,403)
  self.assertEqual(public.post('/api/logout').status_code,200)
  self.assertEqual(public.get('/api/me').status_code,401)
