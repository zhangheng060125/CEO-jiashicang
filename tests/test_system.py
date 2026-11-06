import os,tempfile,unittest,json,io
from pathlib import Path
TEMP=tempfile.TemporaryDirectory();os.environ['HOTEL_DATA_DIR']=TEMP.name
from fastapi.testclient import TestClient
import server as s
from openpyxl import Workbook
class SystemTests(unittest.TestCase):
 def setUp(self):
  with s.db() as c:
   c.execute('DELETE FROM records WHERE kind!="property"');c.execute('DELETE FROM users WHERE username!="admin"');c.execute('DELETE FROM sessions');c.execute('DELETE FROM audit');c.execute('DELETE FROM imports')
  credentials=Path(TEMP.name,'admin-password.txt').read_text().splitlines();self.password=credentials[1].split(': ',1)[1]
  self.client=TestClient(s.app);self.assertEqual(self.client.post('/api/login',json={'username':'admin','password':self.password}).status_code,200)
 def put(self,kind,ext,data,prop='bhl',dataset='actual',status=200):
  r=self.client.post('/api/records/'+kind,json={'dataset':dataset,'property_id':prop,'external_id':ext,'data':data});self.assertEqual(r.status_code,status,r.text);return r.json()
 def order(self,no='O1',amount=1000,prop='bhl',contract=''):
  return self.put('order',no,dict(order_no=no,order_date='2026-11-01',checkin='2026-11-02',checkout='2026-11-04',kind='stay',status='completed',booking_amount=amount,channel='douyin',traffic='paid',contract_code=contract),prop)
 def payment(self,ext,amount,typ='collection',day='2026-11-01',reversal=0,dest='platform',order='O1',status=200):
  return self.put('payment',ext,dict(order_no=order,day=day,type=typ,destination=dest,amount=amount,revenue_reversal=reversal,due_date='2026-11-05'),status=status)
 def fulfill(self,ext,amount,day='2026-11-02',business='room',nights=1,included=False,status=200):
  return self.put('fulfillment',ext,dict(order_no='O1',day=day,business=business,amount=amount,room_nights=nights,included=included,guest_type='not_applicable'),status=status)
 def report(self,start='2026-11-01',end='2026-11-04'):
  r=self.client.get('/api/dashboard',params=dict(dataset='actual',property_id='bhl',start=start,end=end,asof='2026-11-05'));self.assertEqual(r.status_code,200,r.text);return r.json()
 def test_cross_day_package_refund_and_dashboard_drill_agree(self):
  oid=self.order()['id'];self.payment('pay',1000);self.fulfill('night1',400);self.fulfill('night2',400,'2026-11-03');self.fulfill('spa',200,business='spa',nights=0);self.fulfill('breakfast',0,business='dining',nights=0,included=True)
  self.fulfill('bad-breakfast',10,business='dining',nights=0,included=True,status=422)
  self.fulfill('too-much',1,business='spa',nights=0,status=422)
  self.payment('refund',100,'refund','2026-11-04',100)
  r=self.report();self.assertEqual(r['metrics']['revenue'],900);self.assertEqual(r['metrics']['room_nights'],2);self.assertEqual(r['metrics']['room_revenue'],720);self.assertEqual(r['metrics']['adr'],360);self.assertEqual(sum(x['revenue'] or 0 for x in r['lodging_analysis']['room_type']),720)
  self.assertEqual(sum(x['fulfilled_revenue'] for x in r['orders']),r['metrics']['revenue'])
  self.assertEqual(self.report('2026-11-02','2026-11-02')['metrics']['revenue'],600)
  self.assertEqual(self.report('2026-11-03','2026-11-03')['metrics']['revenue'],400)
  self.assertEqual(self.report('2026-11-04','2026-11-04')['metrics']['revenue'],-100)
  drill=self.client.get('/api/order/'+str(oid)).json();self.assertEqual(len([x for x in drill['records'] if x['kind']=='fulfillment']),4)
 def test_prepaid_is_not_revenue_and_settlement_not_duplicate(self):
  self.order();self.payment('pay',1000);r=self.report();self.assertEqual(r['metrics']['advance'],1000);self.assertEqual(r['metrics']['pending'],1000);self.assertEqual(r['metrics']['received'],0)
  self.payment('settle',700,'settlement','2026-11-03',dest='bank');r=self.report();self.assertEqual(r['metrics']['paid_net'],1000);self.assertEqual(r['metrics']['received'],700);self.assertEqual(r['metrics']['pending'],300)
  self.payment('over',400,'settlement','2026-11-03',dest='bank',status=422)
 def test_refund_amount_and_timing_guards(self):
  self.order();self.payment('pay',500);self.payment('over',501,'refund',status=422);self.payment('early',100,'refund','2026-10-30',status=422);self.payment('unfulfilled-reversal',100,'refund','2026-11-02',100,status=422)
 def test_contract_commission_separate_from_park_revenue(self):
  self.put('contract','C',dict(code='C',start='2026-01-01',end='2026-12-31',rate=.1,basis='fulfilled',beneficiary='operator',settlement_days=7))
  self.order(contract='C');self.payment('pay',1000);self.fulfill('room',1000);r=self.report()
  self.assertEqual(r['metrics']['revenue'],1000);self.assertEqual(r['metrics']['commission'],100);self.assertEqual(r['operator']['total_revenue'],100);self.assertEqual(r['metrics']['trade_amount'],1000)
  self.payment('refund',100,'refund','2026-11-04',100);self.assertEqual(self.report()['operator']['total_revenue'],90)
 def test_import_preview_duplicate_conflict_and_atomicity(self):
  self.order();header=['external_id',*s.SCHEMAS['fulfillment']['fields']];row=dict(room_type='',external_id='I1',order_no='O1',day='2026-11-02',business='room',amount=500,room_nights=1,included=False,guest_type='not_applicable',guests=2)
  payload=dict(kind='fulfillment',dataset='actual',property_id='bhl',filename='test.csv',rows=[row]);first=self.client.post('/api/import/commit',json=payload);self.assertEqual(first.json()['inserted'],1)
  second=self.client.post('/api/import/commit',json=payload);self.assertEqual(second.json()['skipped'],1)
  changed={**payload,'rows':[{**row,'amount':400}]};self.assertEqual(self.client.post('/api/import/commit',json=changed).status_code,409)
  batch={**payload,'rows':[{**row,'external_id':'I2','amount':200},{**row,'external_id':'I3','amount':500}]};self.assertEqual(self.client.post('/api/import/commit',json=batch).status_code,422)
  rs=self.client.get('/api/records/fulfillment?dataset=actual&property_id=bhl').json()['records'];self.assertEqual(len(rs),1)
  wb=Workbook();ws=wb.active;ws.append(header);ws.append([row.get(k) for k in header]);buf=io.BytesIO();wb.save(buf)
  preview=self.client.post('/api/import/preview?kind=fulfillment&dataset=actual&property_id=bhl&filename=test.xlsx',content=buf.getvalue());self.assertEqual(preview.status_code,200,preview.text);self.assertEqual(preview.json()['skipped'],1)
  logs=self.client.get('/api/logs?dataset=actual').json()['imports'];self.assertTrue(any(x['status']=='failed' for x in logs))
 def test_backend_scope_role_and_demo_isolation(self):
  oid=self.order()['id'];self.order('O2',prop='jtw')
  r=self.client.post('/api/users',json=dict(username='manager',password='Test-Only-Password-99',role='manager',properties=['jtw']));self.assertEqual(r.status_code,200,r.text)
  manager=TestClient(s.app);manager.post('/api/login',json=dict(username='manager',password='Test-Only-Password-99'))
  self.assertEqual(manager.get('/api/order/'+str(oid)).status_code,403);self.assertEqual(manager.get('/api/records/order?dataset=actual&property_id=bhl').status_code,403)
  rs=manager.get('/api/records/order?dataset=actual').json()['records'];self.assertTrue(all(x['property_id']=='jtw' for x in rs))
  self.assertEqual(manager.post('/api/records/payment',json=dict(dataset='actual',property_id='jtw',external_id='X',data={})).status_code,403)
  self.client.post('/api/users',json=dict(username='ops',password='Test-Only-Password-99',role='operations',properties=['bhl']))
  ops=TestClient(s.app);ops.post('/api/login',json=dict(username='ops',password='Test-Only-Password-99'));self.assertEqual(ops.get('/api/records/cost?dataset=actual').status_code,403)
  demo=TestClient(s.app);demo.post('/api/login',json={'demo':True});self.assertEqual(demo.get('/api/records/order?dataset=actual').status_code,403);self.assertEqual(demo.post('/api/users',json={}).status_code,403)
 def test_issue_redline_requires_evidence_review_and_audit_version(self):
  data=dict(day='2026-11-01',department='kitchen',title='留样缺失',severity='redline',evidence='检查001',owner='餐饮负责人',due_date='2026-11-02',status='open')
  rid=self.put('issue','Q1',data)['id'];row=self.client.get('/api/records/issue?dataset=actual').json()['records'][0]
  body=dict(dataset='actual',property_id='bhl',external_id='Q1',version=1,data={**data,'status':'closed'})
  self.assertEqual(self.client.put('/api/records/issue/'+str(rid),json=body).status_code,422)
  body['data'].update(remediation='已补齐并培训',review_result='复查通过',reviewer='店长');self.assertEqual(self.client.put('/api/records/issue/'+str(rid),json=body).status_code,200)
  self.assertEqual(self.client.put('/api/records/issue/'+str(rid),json=body).status_code,409)
  logs=self.client.get('/api/logs?dataset=actual').json()['audit'];self.assertTrue(any(x['action']=='update' and 'before' in x['detail'] for x in logs))
 def test_missing_cost_and_inventory_do_not_produce_false_profit_or_ratio(self):
  self.order();self.payment('pay',1000);self.fulfill('room',1000);r=self.report();self.assertIsNone(r['metrics']['contribution']);self.assertIsNone(r['metrics']['occupancy']);self.assertIsNone(r['metrics']['revpar'])
  self.put('inventory','I',dict(day='2026-11-02',room_type='标准',physical=10,out_of_service=2,available=8,locked=1,voucher_commitment=2,is_open=True,day_type='workday'))
  self.put('coverage','COV',dict(day='2026-11-02',complete=True,owner='财务'))
  self.put('cost','COST',dict(day='2026-11-02',category='supplies',amount=200,scope='park'))
  r=self.report('2026-11-02','2026-11-02');self.assertEqual(r['metrics']['occupancy'],.125);self.assertEqual(r['metrics']['revpar'],125);self.assertEqual(r['metrics']['contribution'],800)
 def test_privacy_csrf_and_static_whitelist(self):
  self.put('customer','C',dict(code='C',phone_last4='13800138000',day='2026-11-01',owner='客服',status='new'),status=422)
  self.assertEqual(self.client.post('/api/logout',headers={'Origin':'https://evil.example'}).status_code,403)
  self.assertEqual(self.client.get('/.runtime/admin-password.txt').status_code,404);self.assertEqual(self.client.get('/server.py').status_code,404)
 def test_empty_actual_is_unknown_not_zero(self):
  r=self.report();self.assertIsNone(r['metrics']['revenue']);self.assertIsNone(r['metrics']['room_nights']);self.assertIsNone(r['metrics']['trade_amount']);self.assertTrue(all(d['revenue'] is None for d in r['daily']))
 def test_preview_is_non_mutating_and_export_is_scoped(self):
  self.order();row=dict(room_type='',external_id='PREVIEW',order_no='O1',day='2026-11-02',business='room',amount=500,room_nights=1,included=False,guest_type='not_applicable',guests=2)
  header=['external_id',*s.SCHEMAS['fulfillment']['fields']];wb=Workbook();ws=wb.active;ws.append(header);ws.append([row.get(k) for k in header]);buf=io.BytesIO();wb.save(buf)
  preview=self.client.post('/api/import/preview?kind=fulfillment&dataset=actual&property_id=bhl&filename=new.xlsx',content=buf.getvalue());self.assertEqual(preview.json()['inserted'],1)
  self.assertEqual(self.client.get('/api/records/fulfillment?dataset=actual').json()['records'],[])
  export=self.client.get('/api/export/order?dataset=actual&property_id=bhl');self.assertEqual(export.status_code,200);self.assertIn('O1',export.text)
 def test_operator_contract_due_date_and_receipt(self):
  self.put('contract','C',dict(code='C',start='2026-01-01',end='2026-12-31',rate=.1,basis='fulfilled',beneficiary='operator',settlement_days=1))
  self.order(contract='C');self.payment('pay',1000);self.fulfill('room',1000)
  r=self.report();self.assertEqual(r['operator']['pending'],100);self.assertEqual(r['operator']['overdue'],100)
  self.put('operator_entry','RCPT',dict(day='2026-11-04',type='commission_received',amount=60,contract_code='C'))
  r=self.report();self.assertEqual(r['operator']['pending'],40);self.assertEqual(r['operator']['total_revenue'],100)
 def test_consignment_principal_not_recognized_as_revenue_or_advance(self):
  self.put('order','CNS',dict(order_no='CNS',order_date='2026-11-01',checkin='2026-11-02',checkout='2026-11-02',kind='consignment',status='completed',booking_amount=1000,principal_amount=900,channel='miniapp',traffic='organic'))
  self.payment('pay',1000,dest='bank',order='CNS')
  self.put('fulfillment','fee',dict(order_no='CNS',day='2026-11-02',business='consignment_fee',amount=100,room_nights=0,included=False,guest_type='not_applicable'))
  r=self.report();self.assertEqual(r['metrics']['revenue'],100);self.assertEqual(r['metrics']['principal_liability'],900);self.assertEqual(r['metrics']['advance'],0)
  self.payment('principal',900,'principal_payout','2026-11-03',dest='bank',order='CNS')
  r=self.report();self.assertEqual(r['metrics']['principal_liability'],0);self.assertEqual(r['metrics']['paid_net'],1000);self.assertEqual(r['metrics']['received'],1000);self.assertEqual(r['metrics']['revenue'],100)
 def test_cost_business_allocation_and_campaign_split(self):
  self.order();self.payment('pay',1000);self.fulfill('meal',1000,business='dining',nights=0)
  self.put('cost','FOOD',dict(day='2026-11-02',category='food',amount=200,scope='park',business='dining'))
  r=self.report();dining=next(x for x in r['breakdown'] if x['business']=='dining');self.assertEqual(dining['allocated_cost'],200);self.assertEqual(dining['known_contribution'],800)
 def test_targeted_refund_consumes_remaining_rights_without_room_dilution(self):
  self.order();self.payment('pay',1000);self.fulfill('ROOM',800);self.fulfill('SPA',200,business='spa',nights=0)
  self.put('payment','RSPA',dict(order_no='O1',day='2026-11-03',type='refund',destination='platform',amount=200,revenue_reversal=200,fulfillment_ref='SPA'))
  self.payment('remaining',100,'refund','2026-11-04',100)
  r=self.report();self.assertEqual(r['metrics']['room_revenue'],700);self.assertEqual(r['metrics']['revenue'],700)
  spa=next(b for b in r['breakdown'] if b['business']=='spa');self.assertEqual(spa['net_revenue'],0)
  self.put('payment','OVERSPA',dict(order_no='O1',day='2026-11-04',type='refund',destination='platform',amount=1,revenue_reversal=1,fulfillment_ref='SPA'),status=422)
 def test_entitlement_units_expiry_and_product_allocation(self):
  self.put('product','PROD',dict(code='SPA',name='芳疗',business='spa',active=True,unit='次'))
  self.order();self.payment('PAY',1000)
  self.put('entitlement','RIGHT',dict(code='RIGHT',order_no='O1',product_code='SPA',business='spa',quantity=2,cancelled_units=0,allocated_amount=1000,expires_on='2026-11-03'))
  self.put('fulfillment','USE',dict(order_no='O1',day='2026-11-02',business='spa',amount=500,room_nights=0,included=False,guest_type='not_applicable',product_code='SPA',entitlement_code='RIGHT',redeemed_units=1))
  r=self.report();self.assertEqual(r['entitlements'][0]['remaining_units'],1);self.assertEqual(r['metrics']['advance'],500);self.assertEqual(r['products'][0]['revenue'],500)
  self.put('fulfillment','OVER',dict(order_no='O1',day='2026-11-03',business='spa',amount=500,room_nights=0,included=False,guest_type='not_applicable',entitlement_code='RIGHT',redeemed_units=2),status=422)
  self.put('fulfillment','EXPIRED',dict(order_no='O1',day='2026-11-04',business='spa',amount=500,room_nights=0,included=False,guest_type='not_applicable',entitlement_code='RIGHT',redeemed_units=1),status=422)
 def test_sop_failure_creates_task_once_and_redline_survives_high_score(self):
  self.put('sop_item','S',dict(code='S',department='kitchen',title='厨房留样',standard='按时留样',redline=True,active=True))
  check=dict(day='2026-11-02',item_code='S',result='fail',evidence='现场检查',owner='负责人',due_date='2026-11-03')
  rid=self.put('sop_check','CHECK',check)['id'];body=dict(dataset='actual',property_id='bhl',external_id='CHECK',version=1,data={**check,'evidence':'补充现场检查照片编号'})
  self.assertEqual(self.client.put('/api/records/sop_check/'+str(rid),json=body).status_code,200)
  self.put('sop_check','PASS',dict(day='2026-11-03',item_code='S',result='pass',evidence='另一批次合格',owner='负责人',due_date='2026-11-03'))
  result=self.report();q=result['service_quality'];self.assertEqual(q['active_redlines'],1);self.assertFalse(q['can_show_pass']);self.assertEqual(q['pass_rate'],.5)
  issues=self.client.get('/api/records/issue?dataset=actual').json()['records'];self.assertEqual(len(issues),1)
  issue=issues[0];self.assertEqual(self.client.delete('/api/records/issue/'+str(issue['id'])+'?version=1').status_code,409)
  changed={**issue['data'],'severity':'normal'};self.assertEqual(self.client.put('/api/records/issue/'+str(issue['id']),json=dict(dataset='actual',property_id='bhl',external_id=issue['external_id'],version=1,data=changed)).status_code,422)
 def test_identified_cohort_excludes_aggregate_exposure_and_unknown_identity(self):
  self.put('campaign','LIVE',dict(code='LIVE',day='2026-11-01',channel='douyin',format='live',traffic='organic',impressions=10000,viewers=3000,consultations=10,spend=0))
  for who in ['A','B']:self.put('touchpoint','VIEW-'+who,dict(day='2026-11-01',customer_code=who,campaign_code='LIVE',stage='view',evidence='platform-event-'+who))
  self.put('touchpoint','CONSULT',dict(day='2026-11-01',customer_code='A',campaign_code='LIVE',stage='consult',evidence='event-3'))
  self.put('order','O1',dict(order_no='O1',order_date='2026-11-01',checkin='2026-11-02',checkout='2026-11-04',kind='stay',status='completed',booking_amount=1000,customer_code='A',channel='douyin',traffic='organic',campaign_code='LIVE'))
  self.payment('P',1000);self.fulfill('F',1000)
  cohort=self.report()['cohorts'][0];self.assertEqual(cohort['viewers'],2);self.assertEqual(cohort['paid'],1);self.assertEqual(cohort['paid_conversion'],.5);self.assertEqual(cohort['fulfilled'],1)
 def test_budget_channel_comparison_no_double_count(self):
  self.order();self.payment('P',1000);self.fulfill('F',1000);self.put('cost','C',dict(day='2026-11-02',category='supplies',amount=100,scope='park',order_no='O1'))
  for channel,budget in [('',800),('douyin',500)]:self.put('target','TARGET-'+(channel or 'all'),dict(start='2026-11-01',end='2026-11-04',channel=channel,scenario='budget',revenue=budget,cost=80,owner='预算负责人'))
  r=self.report();self.assertEqual(r['metrics']['revenue'],1000);self.assertEqual(len(r['target_comparisons']),2);self.assertEqual(r['target_comparisons'][0]['actual_revenue'],1000);self.assertEqual(r['target_comparisons'][1]['revenue_gap'],500)
 def test_configurable_alert_owner_idempotent_assignment_and_recurrence(self):
  from datetime import date,timedelta
  for i in range(7):
   d=(date(2026,11,5)+timedelta(days=i)).isoformat();self.put('inventory','I'+d,dict(day=d,room_type='标准',physical=10,out_of_service=0,available=10,locked=0,voucher_commitment=0,is_open=True,day_type='workday'))
  self.put('alert_rule','RULE',dict(code='booking7',channel='',enabled=True,threshold=.5,severity='major',owner='收益负责人',deadline_days=2))
  alert=next(a for a in self.report()['alerts'] if a['rule_code']=='booking7');self.assertEqual(alert['owner'],'收益负责人');self.assertEqual(alert['due_date'],'2026-11-07')
  payload=dict(dataset='actual',property_id='bhl',scope_property='bhl',start='2026-11-01',end='2026-11-04',asof='2026-11-05',alert_key=alert['alert_key'],owner='收益负责人',due_date='2026-11-07')
  first=self.client.post('/api/alerts/assign',json=payload);self.assertEqual(first.status_code,200,first.text)
  second=self.client.post('/api/alerts/assign',json=payload);self.assertEqual(first.json()['id'],second.json()['id']);self.assertTrue(second.json()['reused'])
  row=next(x for x in self.client.get('/api/records/issue?dataset=actual').json()['records'] if x['id']==first.json()['id'])
  data={**row['data'],'status':'closed','remediation':'方案已执行','review_result':'复查确认','reviewer':'店长'}
  self.assertEqual(self.client.put('/api/records/issue/'+str(row['id']),json={**{k:row[k] for k in ['dataset','property_id','external_id','version']},'data':data}).status_code,200)
  alert=next(a for a in self.report()['alerts'] if a['rule_code']=='booking7');self.assertEqual(alert['task_status'],'recurrence')
 def test_permission_edit_revokes_old_sessions_and_self_password_rotation(self):
  self.client.post('/api/users',json=dict(username='staff',password='Test-Only-Password-99',role='manager',properties=['bhl']))
  staff=TestClient(s.app);staff.post('/api/login',json=dict(username='staff',password='Test-Only-Password-99'))
  uid=next(u['id'] for u in self.client.get('/api/users').json()['users'] if u['username']=='staff')
  self.assertEqual(self.client.put('/api/users/'+str(uid),json=dict(role='finance',properties=['jtw'],active=True)).status_code,200)
  self.assertEqual(staff.get('/api/me').status_code,401);staff.post('/api/login',json=dict(username='staff',password='Test-Only-Password-99'))
  self.assertEqual(staff.get('/api/records/order?dataset=actual&property_id=bhl').status_code,403)
  self.assertEqual(staff.post('/api/account/password',json=dict(old_password='wrong',new_password='New-Test-Password-123')).status_code,403)
  self.assertEqual(staff.post('/api/account/password',json=dict(old_password='Test-Only-Password-99',new_password='New-Test-Password-123')).status_code,200)
  self.assertEqual(staff.get('/api/me').status_code,401);self.assertEqual(staff.post('/api/login',json=dict(username='staff',password='New-Test-Password-123')).status_code,200)
 def test_json_validation_privacy_and_export_period(self):
  self.assertEqual(self.client.post('/api/login',json=[]).status_code,400)
  self.assertEqual(self.client.post('/api/login',content='{').status_code,400)
  self.assertEqual(self.client.get('/api/dashboard?end=bad-date').status_code,422)
  self.put('review','R',dict(day='2026-11-02',channel='微信',rating=2,category='service',content='联系13800138000，邮箱guest@example.com',owner='客服',status='open'))
  row=self.client.get('/api/records/review?dataset=actual').json()['records'][0];self.assertNotIn('13800138000',row['data']['content']);self.assertNotIn('guest@example.com',row['data']['content'])
  export=self.client.get('/api/export/review?dataset=actual&start=2026-11-03&end=2026-11-04');self.assertNotIn('微信',export.text)
 def test_paid_net_commission_ignores_consignment_principal_outflow(self):
  self.put('contract','C',dict(code='C',start='2026-01-01',end='2026-12-31',rate=.1,basis='paid_net',beneficiary='operator',settlement_days=1))
  self.put('order','CNS',dict(order_no='CNS',order_date='2026-11-01',checkin='2026-11-02',checkout='2026-11-02',kind='consignment',status='confirmed',booking_amount=1000,principal_amount=900,channel='miniapp',traffic='organic',contract_code='C'))
  self.payment('PAY',1000,dest='bank',order='CNS');self.payment('OUT',900,'principal_payout','2026-11-03',dest='bank',order='CNS')
  r=self.report();self.assertEqual(r['operator']['commission_revenue'],100);self.assertEqual(r['operator']['balances'][0]['earned'],100)
 def test_platform_fee_closes_pending_without_duplicate_cost_or_payment(self):
  self.put('contract','C',dict(code='C',start='2026-01-01',end='2026-12-31',rate=.1,basis='fulfilled',beneficiary='external',settlement_days=1))
  self.order(contract='C');self.payment('P',1000);self.fulfill('F',1000)
  self.payment('FEE',100,'platform_fee','2026-11-03');self.payment('SETTLE',900,'settlement','2026-11-04',dest='bank')
  r=self.report();self.assertEqual(r['metrics']['pending'],0);self.assertEqual(r['metrics']['received'],900);self.assertEqual(r['metrics']['paid_net'],1000);self.assertEqual(r['metrics']['commission'],100);self.assertEqual(r['metrics']['platform_fees_withheld'],100)
 def test_missing_known_room_type_blocks_false_occupancy(self):
  self.order();self.payment('P',1000);self.fulfill('F',1000)
  for day,room in [('2026-11-02','A'),('2026-11-02','B'),('2026-11-03','A')]:
   self.put('inventory',day+room,dict(day=day,room_type=room,physical=10,out_of_service=0,available=10,locked=0,voucher_commitment=0,is_open=True,day_type='workday'))
  r=self.report('2026-11-02','2026-11-03');self.assertFalse(r['metrics']['inventory_complete']);self.assertIsNone(r['metrics']['occupancy'])
 def test_closed_room_type_does_not_mark_entire_property_cost_complete(self):
  self.order();self.payment('P',1000);self.fulfill('F',1000)
  for room,opened in [('A',True),('B',False)]:
   self.put('inventory',room,dict(day='2026-11-02',room_type=room,physical=10,out_of_service=0,available=10 if opened else 0,locked=0,voucher_commitment=0,is_open=opened,day_type='workday'))
  r=self.report('2026-11-02','2026-11-02');self.assertFalse(r['metrics']['cost_complete']);self.assertEqual(r['metrics']['missing_cost_days'],1)
 def test_concurrent_version_update_has_exactly_one_winner(self):
  from concurrent.futures import ThreadPoolExecutor
  data=dict(day='2026-11-01',department='rooms',title='检查',severity='normal',evidence='E',owner='A',due_date='2026-11-02',status='open')
  rid=self.put('issue','RACE',data)['id']
  def update(owner):
   client=TestClient(s.app);client.cookies.update(self.client.cookies)
   return client.put('/api/records/issue/'+str(rid),json=dict(dataset='actual',property_id='bhl',external_id='RACE',version=1,data={**data,'owner':owner})).status_code
  with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(update,['B','C']))
  self.assertEqual(sorted(statuses),[200,409])
 def test_deleted_unreferenced_project_stays_deleted_after_restart(self):
  row=next(r for r in self.client.get('/api/records/property?dataset=actual').json()['records'] if r['property_id']=='other')
  self.assertEqual(self.client.delete('/api/records/property/'+str(row['id'])+'?version='+str(row['version'])).status_code,200)
  s.init_db()
  self.assertFalse(any(r['property_id']=='other' for r in self.client.get('/api/records/property?dataset=actual').json()['records']))
 def test_database_persistence_across_connections(self):
  self.order()
  with s.db() as c:self.assertEqual(len(s.records(c,'actual','order')),1)
  s.init_db()
  with s.db() as c:self.assertEqual(len(s.records(c,'actual','order')),1)
if __name__=='__main__':unittest.main()
