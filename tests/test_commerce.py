import csv,io,json,unittest
from fastapi.testclient import TestClient
import test_system as system

s=system.s
PROP='youxuan'

class CommerceTests(unittest.TestCase):
    def setUp(self):system.SystemTests.setUp(self)
    put=system.SystemTests.put
    def product(self,code='P',mode='self',owned=True,typ='physical'):
        return self.put('commerce_product',code,dict(code=code,name='测试商品'+code,mode=mode,product_type=typ,supplier='测试合作方',owned_stock=owned,active=True,unit='件',owner='产品负责人'),PROP)
    def line(self,no='C1',product='P',mode='self',recognition='gross',collector='platform',delivery='pickup',amount=100,qty=1,**extra):
        return self.put('commerce_line',no+extra.get('line_no','1'),dict(order_no=no,line_no='1',order_date='2026-11-02',product_code=product,mode=mode,channel='miniapp',traffic='organic',quantity=qty,cancelled_quantity=0,amount=amount,recognition=recognition,collector=collector,delivery=delivery,status='confirmed',cost_complete=True,owner='优选负责人')|extra,PROP)
    def event(self,typ,amount,no='C1',ext=None,day='2026-11-02',status=200,**extra):
        ext=ext or typ
        return self.put('commerce_event',ext,dict(order_no=no,line_no='1',day=day,type=typ,amount=amount,quantity=0,recognized_amount=0 if typ=='refund' else None,supplier_amount=0,fee_amount=0,funds_location='bank',source_ref=ext,owner='财务')|extra,PROP,status=status)
    def report(self,start='2026-11-02',end='2026-11-02',prop=PROP,client=None):
        r=(client or self.client).get('/api/dashboard',params=dict(dataset='actual',property_id=prop,start=start,end=end,asof='2026-11-05'));self.assertEqual(r.status_code,200,r.text);return r.json()
    def cost(self,amount,category='goods',ext='COGS',**extra):
        return self.put('commerce_cost',ext,dict(day='2026-11-02',category=category,amount=amount,order_no='C1',line_no='1',source_ref=ext,owner='财务')|extra,PROP)
    def cover(self):self.put('coverage','COV',dict(day='2026-11-02',complete=True,owner='财务'),PROP)

    def test_gross_sales_cash_delivery_cost_and_park_separation(self):
        self.product();self.line();self.event('payment',100)
        self.assertIsNone(self.report()['commerce']['metrics']['recognized_income'])
        self.event('fulfilled',100,quantity=1)
        self.cost(60);self.cover();r=self.report(prop='');m=r['commerce']['metrics']
        self.assertEqual(m['paid_gmv'],100);self.assertEqual(m['recognized_income'],100);self.assertEqual(m['contribution'],40)
        self.assertEqual(m['received'],100);self.assertIsNone(r['metrics']['revenue']);self.assertIsNone(r['metrics']['trade_amount'])

    def test_net_joint_trade_is_not_platform_income_and_principal_not_revenue(self):
        self.product(mode='joint',owned=False);self.line(mode='joint',recognition='net')
        self.event('payment',100,funds_location='channel')
        self.event('fulfilled',100,quantity=1,recognized_amount=20,supplier_amount=80,funds_location='')
        self.event('settlement',98,fee_amount=2);self.event('supplier_payout',80)
        self.cover();m=self.report()['commerce']['metrics']
        self.assertEqual(m['paid_gmv'],100);self.assertEqual(m['recognized_income'],20);self.assertEqual(m['contribution'],18)
        self.assertEqual(m['pending_channel'],0);self.assertEqual(m['supplier_payable'],0)
        self.event('refund',100,recognized_amount=20,supplier_amount=80,quantity=1,ext='AFTER-PAYOUT')
        m=self.report()['commerce']['metrics'];self.assertEqual(m['recognized_income'],0);self.assertEqual(m['supplier_recovery'],80);self.assertEqual(m['contribution'],-2)

    def test_affiliate_supplier_receipts_and_commission_refund_balances(self):
        self.product(mode='affiliate',owned=False,typ='voucher');self.line(mode='affiliate',recognition='net',collector='supplier',delivery='redeem')
        self.event('payment',100,funds_location='supplier');self.event('fulfilled',100,quantity=1,recognized_amount=15,funds_location='')
        self.event('commission_received',10);m=self.report()['commerce']['metrics']
        self.assertEqual(m['recognized_income'],15);self.assertEqual(m['received'],10);self.assertEqual(m['commission_pending'],5)
        self.event('refund',100,quantity=1,recognized_amount=15,funds_location='supplier')
        m=self.report()['commerce']['metrics'];self.assertEqual(m['commission_returnable'],10)
        self.event('commission_return',10);self.assertEqual(self.report()['commerce']['metrics']['commission_returnable'],0)

    def test_unknown_contract_or_net_fee_never_fabricates_income(self):
        self.product(mode='joint',owned=False);self.line(mode='joint',recognition='unconfirmed')
        self.event('payment',100);self.event('fulfilled',100,quantity=1,recognized_amount=None)
        m=self.report()['commerce']['metrics'];self.assertEqual(m['paid_gmv'],100);self.assertIsNone(m['recognized_income']);self.assertIsNone(m['contribution'])

    def test_old_order_balances_survive_period_filter_and_cross_day_income(self):
        self.product();self.line();self.event('payment',100,funds_location='channel')
        self.event('fulfilled',100,day='2026-11-03',quantity=1)
        r=self.report('2026-11-04','2026-11-04')['commerce'];self.assertIsNone(r['metrics']['paid_gmv']);self.assertEqual(r['metrics']['pending_channel'],100)
        self.assertIsNone(r['metrics']['recognized_income']);self.assertEqual(len(r['lines']),1)
        self.assertEqual(self.report('2026-11-03','2026-11-03')['commerce']['metrics']['recognized_income'],100)

    def test_quantities_settlement_and_duplicate_source_are_guarded(self):
        self.product();self.line(delivery='shipping');self.event('payment',100,funds_location='channel')
        self.event('fulfilled',100,quantity=1,status=422)
        self.event('shipped',0,quantity=1);self.event('fulfilled',100,quantity=1)
        self.event('settlement',101,status=422)
        self.event('refund',101,recognized_amount=101,status=422)
        self.event('refund',10,recognized_amount=10,quantity=0,ext='REF-A')
        self.event('refund',10,recognized_amount=10,quantity=0,ext='REF-B',source_ref='REF-A',status=422)

    def test_multi_line_order_and_matching_payment_refund_cohort(self):
        self.product();self.line(qty=1,amount=60)
        self.line(qty=1,amount=40,line_no='2')
        self.event('payment',60,ext='PAY1');self.event('payment',40,ext='PAY2',line_no='2')
        self.event('refund',10,ext='REF2',line_no='2',recognized_amount=0)
        m=self.report()['commerce']['metrics'];self.assertEqual(m['paid_orders'],1);self.assertEqual(m['average_order'],100);self.assertEqual(m['cohort_refund_rate'],1)

    def test_traffic_product_rows_do_not_inflate_platform_uv(self):
        self.product()
        base=dict(day='2026-11-02',channel='miniapp',visitors=100,paying_visitors=10,observed_through='2026-11-03',cohort_complete=True,source_ref='UV1',owner='运营')
        self.put('commerce_traffic','PLATFORM',base|dict(level='platform'),PROP)
        self.put('commerce_traffic','PRODUCT',base|dict(level='product',product_code='P',source_ref='UV2'),PROP)
        m=self.report()['commerce']['metrics'];self.assertEqual(m['daily_uv_sum'],100);self.assertEqual(m['visitor_conversion'],.1)

    def test_stock_missing_is_not_zero_and_merchant_stock_not_owned(self):
        self.product();self.product('P2');m=self.report()['commerce']['metrics'];self.assertEqual(m['missing_stock'],2);self.assertIsNone(m['out_of_stock'])
        self.put('commerce_stock','ZERO',dict(day='2026-11-02',product_code='P',warehouse='WH',on_hand=0,reserved=0,unusable=0,source_ref='WH1',owner='库管'),PROP)
        m=self.report()['commerce']['metrics'];self.assertEqual(m['missing_stock'],1);self.assertEqual(m['out_of_stock'],1)
        self.product('AFF',mode='affiliate',owned=False)
        self.put('commerce_stock','MERCHANT',dict(day='2026-11-02',product_code='AFF',warehouse='WH',on_hand=10,reserved=0,unusable=0,source_ref='WH2',owner='库管'),PROP,status=422)

    def test_linked_park_order_does_not_duplicate_park_turnover(self):
        self.put('order','HOTEL',dict(order_no='HOTEL',order_date='2026-11-02',checkin='2026-11-02',checkout='2026-11-03',kind='stay',status='completed',booking_amount=1000,channel='miniapp',traffic='organic'))
        self.put('fulfillment','HOTEL-F',dict(order_no='HOTEL',day='2026-11-02',business='room',amount=1000,room_nights=1,included=False,guest_type='not_applicable'))
        self.product(mode='affiliate',owned=False,typ='voucher');self.line(mode='affiliate',recognition='net',collector='supplier',delivery='redeem',amount=1000,park_property='bhl',park_order='HOTEL')
        self.event('payment',1000,funds_location='supplier');self.event('fulfilled',1000,quantity=1,recognized_amount=80,funds_location='')
        r=self.report(prop='');self.assertEqual(r['metrics']['trade_amount'],1000);self.assertEqual(r['metrics']['revenue'],1000);self.assertEqual(r['commerce']['metrics']['paid_gmv'],1000);self.assertEqual(r['commerce']['metrics']['recognized_income'],80)

    def test_operations_cannot_read_finance_or_create_fake_cost_confirmation(self):
        self.product();line=self.line();self.event('payment',100);self.event('fulfilled',100,quantity=1);self.cost(60)
        self.client.post('/api/users',json=dict(username='yx-ops',password='Only-For-Test-123456!',role='operations',properties=[PROP]))
        ops=TestClient(s.app);ops.post('/api/login',json=dict(username='yx-ops',password='Only-For-Test-123456!'))
        r=self.report(client=ops)['commerce'];self.assertEqual(r['metrics']['paid_gmv'],100);self.assertNotIn('recognized_income',r['metrics']);self.assertEqual(r['costs'],[])
        events=ops.get('/api/records/commerce_event?dataset=actual').json()['records'];self.assertEqual(len(events),1);self.assertNotIn('recognized_amount',events[0]['data'])
        self.assertEqual(ops.get('/api/records/commerce_cost?dataset=actual').status_code,403)
        self.assertEqual(ops.get('/api/dashboard?dataset=actual&property_id=bhl').status_code,403)
        body=dict(dataset='actual',property_id=PROP,external_id='FAKE',data=dict(order_no='FAKE',line_no='1',order_date='2026-11-02',product_code='P',mode='self',channel='miniapp',traffic='organic',quantity=1,amount=100,recognition='unconfirmed',collector='platform',delivery='pickup',status='confirmed',cost_complete=True,owner='运营'))
        self.assertEqual(ops.post('/api/records/commerce_line',json=body).status_code,403)
        self.assertNotIn('recognized_amount',ops.get('/api/export/commerce_event?dataset=actual').content.decode('utf-8-sig').splitlines()[0])

    def test_commerce_import_is_persistent_and_duplicate_safe(self):
        header=['external_id',*s.SCHEMAS['commerce_product']['fields']]
        row=dict(external_id='IMPORT-P',code='IP',name='导入产品',mode='retail',product_type='physical',owned_stock='true',active='true',unit='件',owner='运营')
        out=io.StringIO();w=csv.writer(out);w.writerow(header);w.writerow([row.get(k,'') for k in header])
        url='/api/import/preview?kind=commerce_product&dataset=actual&property_id=youxuan&filename=product.csv'
        first=self.client.post(url,content=out.getvalue().encode());self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.client.post('/api/import/commit',json=first.json()).status_code,200)
        repeat=self.client.post(url,content=out.getvalue().encode());self.assertEqual(repeat.json()['skipped'],1)
        self.assertEqual(len(self.client.get('/api/records/commerce_product?dataset=actual').json()['records']),1)

    def test_spa_rename_migration_preserves_other_fields_and_does_not_resurrect_deleted_projects(self):
        with s.db() as c:
            r=c.execute("SELECT * FROM records WHERE kind='property' AND dataset='actual' AND property_id='spa'").fetchone()
            old=json.loads(r['payload']);old.update(name='B05 芳疗 SPA',physical_rooms=17,note='历史B05说明')
            c.execute('UPDATE records SET payload=? WHERE id=?',(json.dumps(old),r['id']))
            c.execute("DELETE FROM app_migrations WHERE name='v17_select_and_spa'")
        s.init_db()
        with s.db() as c:
            r=c.execute("SELECT payload FROM records WHERE kind='property' AND dataset='actual' AND property_id='spa'").fetchone();value=json.loads(r['payload'])
            self.assertEqual(value['name'],'芳疗SPA');self.assertEqual(value['physical_rooms'],17);self.assertNotIn('B05',value['note'])
            c.execute("DELETE FROM records WHERE kind='property' AND dataset='demo' AND property_id='youxuan'")
        s.init_db()
        with s.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM records WHERE kind='property' AND dataset='demo' AND property_id='youxuan'").fetchone())
            c.execute("INSERT INTO records(kind,dataset,property_id,external_id,payload,updated_at) VALUES('property','demo','youxuan','youxuan',?,?)",(json.dumps(dict(code=PROP,name='森活优选',business='commerce',status='unconfirmed',planned_rooms=None,physical_rooms=None,note='')),s.NOW()))
