import csv
import io
import unittest
from fastapi.testclient import TestClient
import test_system as system
import sectors

s=system.s


class SectorTests(unittest.TestCase):
    def setUp(self):system.SystemTests.setUp(self)
    put=system.SystemTests.put
    def report(self,prop='bhcs',start='2026-11-02',end='2026-11-02',client=None):
        r=(client or self.client).get('/api/dashboard',params=dict(dataset='actual',property_id=prop,start=start,end=end,asof='2026-11-05'))
        self.assertEqual(r.status_code,200,r.text);return r.json()
    def sale(self,prop,business,amount,day='2026-11-02',guests=10,no='SALE'):
        self.put('order',no,dict(order_no=no,order_date=day,checkin=day,checkout=day,kind='voucher',status='completed',booking_amount=amount,channel='offline',traffic='organic'),prop)
        self.put('payment',no+'-PAY',dict(order_no=no,day=day,type='collection',destination='bank',amount=amount,revenue_reversal=0),prop)
        self.put('fulfillment',no+'-F',dict(order_no=no,day=day,business=business,amount=amount,room_nights=1 if business=='room' else 0,included=False,guest_type='walkin' if business=='dining' else 'not_applicable',guests=guests),prop)
    def daily(self,prop,business,day='2026-11-02',**extra):
        return self.put('business_day',business+day,dict(day=day,business=business,is_open=True,complete=True,owner='测试业务负责人')|extra,prop)

    def test_paid_covers_and_targeted_refund_do_not_dilute_with_free_breakfast(self):
        self.sale('bhl','room',1200,no='PACKAGE')
        with s.db() as c:
            line=next(r for r in s.records(c,'actual','fulfillment',['bhl']))
        self.client.put('/api/records/fulfillment/'+str(line['id']),json=dict(dataset='actual',property_id='bhl',external_id=line['external_id'],version=line['version'],data={**line['data'],'amount':800}))
        self.put('fulfillment','DINING',dict(order_no='PACKAGE',day='2026-11-02',business='dining',amount=300,room_nights=0,included=False,guest_type='walkin',guests=3),'bhl')
        self.put('fulfillment','SPA',dict(order_no='PACKAGE',day='2026-11-02',business='spa',amount=100,room_nights=0,included=False,guest_type='not_applicable',guests=1),'bhl')
        self.put('fulfillment','BREAKFAST',dict(order_no='PACKAGE',day='2026-11-02',business='dining',amount=0,room_nights=0,included=True,guest_type='resident',guests=2),'bhl')
        before=self.report('bhl');d=before['sectors']['dining'];self.assertEqual(d['metrics']['average_spend'],100);self.assertEqual(d['metrics']['paid_guests'],3);self.assertEqual(d['metrics']['included_guests'],2)
        self.put('payment','DINING-REFUND',dict(order_no='PACKAGE',day='2026-11-02',type='refund',destination='bank',amount=300,revenue_reversal=300,fulfillment_ref='DINING'),'bhl')
        r=self.report('bhl');self.assertEqual(r['sectors']['room']['metrics']['revenue'],800);self.assertEqual(r['sectors']['dining']['metrics']['revenue'],0)
        self.assertEqual(r['sectors']['dining']['metrics']['average_spend'],0)
        self.assertEqual(sum(o['revenue'] for o in r['sectors']['dining']['orders']),0)
        self.assertEqual(r['sectors']['dining']['guest_groups'][1]['revenue'],0)
        self.assertEqual(sum(x['metrics']['revenue'] or 0 for x in r['sectors'].values()),r['metrics']['revenue'])

    def test_weighted_table_turnover_and_missing_days_are_unknown(self):
        self.daily('bhcs','dining',available_tables=10,meal_periods=2,served_tables=40)
        r=self.report(end='2026-11-03')['sectors']['dining'];self.assertEqual(r['missing_days'],1);self.assertIsNone(r['metrics']['table_turns'])
        self.daily('bhcs','dining','2026-11-03',available_tables=20,meal_periods=2,served_tables=40)
        r=self.report(end='2026-11-03')['sectors']['dining'];self.assertAlmostEqual(r['metrics']['table_turns'],80/60)
        self.assertFalse(any(c['key'] in ['occupancy','adr','revpar','nights'] for c in r['cards']))

    def test_food_and_waste_ratios_wait_for_operating_days_and_finance_confirmation(self):
        self.sale('bhcs','dining',1000)
        self.daily('bhcs','dining',available_tables=10,meal_periods=2,served_tables=20,waste_cost=30)
        self.put('cost','FOOD',dict(day='2026-11-02',category='food',amount=300,scope='park',business='dining'),'bhcs')
        self.assertIsNone(self.report()['sectors']['dining']['metrics']['food_cost_ratio'])
        self.put('coverage','FOOD-CONFIRMED',dict(day='2026-11-02',complete=True,owner='财务'),'bhcs')
        m=self.report()['sectors']['dining']['metrics'];self.assertEqual(m['food_cost_ratio'],.3);self.assertEqual(m['waste_ratio'],.1)
        r=self.report(end='2026-11-03');self.assertIsNone(r['sectors']['dining']['metrics']['food_cost_ratio'])
        self.assertEqual(r['metrics']['cost'],300)

    def test_seasonal_calendar_excludes_closed_days_and_separates_closed_day_refund(self):
        self.sale('water','water',1000,guests=100)
        self.sale('water','water',2000,'2026-11-03',guests=200,no='SECOND')
        self.daily('water','water',visitors=100,daily_capacity=200,safety_incidents=0)
        self.daily('water','water','2026-11-03',visitors=200,daily_capacity=400,safety_incidents=0)
        self.daily('water','water','2026-11-04',is_open=False,visitors=0,daily_capacity=0,safety_incidents=0)
        for day in ['2026-11-02','2026-11-03']:self.put('coverage','COV-'+day,dict(day=day,complete=True,owner='测试财务'),'water')
        self.put('payment','LATER-REFUND',dict(order_no='SALE',day='2026-11-04',type='refund',destination='bank',amount=100,revenue_reversal=100,fulfillment_ref='SALE-F'),'water')
        r=self.report('water',end='2026-11-04');m=r['sectors']['water']['metrics']
        self.assertEqual(m['visitors'],300);self.assertEqual(m['operating_days'],2);self.assertEqual(m['capacity_usage'],.5)
        self.assertEqual(m['revenue'],2900);self.assertEqual(m['daily_revenue'],1500);self.assertEqual(m['safety_incidents'],0)
        self.assertEqual(r['metrics']['missing_cost_days'],0)
        self.assertIsNone(r['metrics']['occupancy']);self.assertEqual(r['lodging_analysis']['property'],[])
        self.assertFalse(any('房量' in a['title'] or '预订低于' in a['title'] for a in r['alerts']))

    def test_spa_appointments_minutes_productivity_and_unchecked_quantities(self):
        self.sale('spa','spa',1500,guests=15)
        row=self.daily('spa','spa',visitors=15,appointments=20,completed_appointments=12,available_minutes=1800,used_minutes=900,labor_hours=30)
        m=self.report('spa')['sectors']['spa']['metrics'];self.assertEqual(m['appointment_completion'],.6);self.assertEqual(m['time_usage'],.5);self.assertEqual(m['average_spend'],100);self.assertEqual(m['labor_productivity'],50)
        record=self.client.get('/api/records/business_day?dataset=actual&property_id=spa').json()['records'][0]
        self.client.put('/api/records/business_day/'+str(row['id']),json=dict(dataset='actual',property_id='spa',external_id=record['external_id'],version=record['version'],data={**record['data'],'complete':False}))
        self.assertIsNone(self.report('spa')['sectors']['spa']['metrics']['visitors'])

    def test_closed_day_refund_does_not_invent_zero_revenue_for_missing_open_day_ledger(self):
        self.sale('water','water',1000,day='2026-11-01')
        self.daily('water','water',visitors=10,daily_capacity=200,safety_incidents=0)
        self.daily('water','water','2026-11-03',is_open=False,visitors=0,daily_capacity=0,safety_incidents=0)
        self.put('payment','ONLY-CLOSED-REFUND',dict(order_no='SALE',day='2026-11-03',type='refund',destination='bank',amount=100,revenue_reversal=100),'water')
        d=self.report('water',end='2026-11-03')['sectors']['water']
        self.assertEqual(d['metrics']['revenue'],-100);self.assertIsNone(d['metrics']['daily_revenue'])
        self.assertEqual(d['orders'][0]['revenue'],-100)

    def test_daily_business_keys_invalid_quantities_and_nonhotel_targets(self):
        self.daily('bhcs','dining',available_tables=10,meal_periods=2,served_tables=20)
        self.put('business_day','DUPLICATE',dict(day='2026-11-02',business='dining',is_open=True,complete=True,owner='核对人'),'bhcs',status=422)
        self.put('business_day','WRONG-FIELD',dict(day='2026-11-03',business='dining',is_open=True,complete=True,visitors=10,owner='核对人'),'bhcs',status=422)
        self.put('business_day','OVER-APPT',dict(day='2026-11-02',business='spa',is_open=True,complete=True,appointments=10,completed_appointments=11,owner='核对人'),'spa',status=422)
        self.put('target','DINING-OCC',dict(start='2026-11-02',end='2026-11-02',scenario='budget',occupancy=.5,owner='经理'),'bhcs',status=422)
        self.assertEqual(len(self.client.get('/api/records/business_day?dataset=actual').json()['records']),1)

    def test_compact_template_preview_commit_and_repeat_import(self):
        r=self.client.get('/api/template/business_day?business=dining');self.assertEqual(r.status_code,200)
        header=next(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))));self.assertEqual(header,['external_id',*sectors.template_fields('dining')]);self.assertNotIn('visitors',header)
        row=dict(external_id='POS-DAILY-1',day='2026-11-02',business='dining',is_open='true',complete='true',available_tables=10,meal_periods=2,served_tables=20,owner='POS核对人')
        out=io.StringIO();writer=csv.writer(out);writer.writerow(header);writer.writerow([row.get(k,'') for k in header]);content=out.getvalue().encode()
        url='/api/import/preview?kind=business_day&dataset=actual&property_id=bhcs&filename=dining.csv&business=dining'
        first=self.client.post(url,content=content);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['inserted'],1);self.assertEqual(self.client.post('/api/import/commit',json=first.json()).status_code,200)
        second=self.client.post(url,content=content);self.assertEqual(second.status_code,200,second.text);self.assertEqual(second.json()['skipped'],1)
        self.assertEqual(self.client.post('/api/import/commit',json=second.json()).status_code,200)

    def test_operations_finance_redaction_and_property_scope(self):
        self.sale('bhcs','dining',1000)
        self.daily('bhcs','dining',available_tables=10,meal_periods=2,served_tables=20,waste_cost=25)
        self.put('cost','FOOD',dict(day='2026-11-02',category='food',amount=300,scope='park',business='dining'),'bhcs')
        self.client.post('/api/users',json=dict(username='test-ops',password='Only-For-Test-12345!',role='operations',properties=['bhcs']))
        ops=TestClient(s.app);self.assertEqual(ops.post('/api/login',json=dict(username='test-ops',password='Only-For-Test-12345!')).status_code,200)
        d=self.report(client=ops)['sectors']['dining'];self.assertEqual(d['costs'],[]);self.assertNotIn('food_cost',d['metrics']);self.assertNotIn('waste_cost',d['operating_records'][0]);self.assertFalse(any(c['financial'] for c in d['cards']))
        self.assertNotIn('waste_cost',ops.get('/api/records/business_day?dataset=actual').json()['records'][0]['data'])
        self.assertNotIn('waste_cost',ops.get('/api/export/business_day?dataset=actual').content.decode('utf-8-sig').splitlines()[0])
        self.assertEqual(ops.get('/api/dashboard?dataset=actual&property_id=water').status_code,403)
        self.daily('bhcs','spa',visitors=8,appointments=10,completed_appointments=8)
        scoped=ops.get('/api/records/business_day?dataset=actual&business=dining').json()['records'];self.assertEqual(len(scoped),1);self.assertEqual(scoped[0]['data']['business'],'dining')
        exported=ops.get('/api/export/business_day?dataset=actual&business=dining').content.decode('utf-8-sig')
        self.assertEqual(len(list(csv.DictReader(io.StringIO(exported)))),1)

    def test_nonhotel_calendar_does_not_change_room_future_denominator(self):
        self.put('inventory','ROOM-INV',dict(day='2026-11-05',room_type='客房',physical=10,out_of_service=0,available=10,locked=0,voucher_commitment=0,is_open=True,day_type='workday'),'bhl')
        self.put('inventory','LEGACY-NONHOTEL',dict(day='2026-11-05',room_type='旧餐厅日历',physical=1000,out_of_service=0,available=1000,locked=0,voucher_commitment=0,is_open=True,day_type='workday'),'bhcs')
        # Planning the other hotels limits the denominator to the configured hotel.
        with s.db() as c:
            for row in s.records(c,'actual','property'):
                if row['property_id'] in ['jtw','520']:
                    data={**row['data'],'status':'planning'}
                    c.execute('UPDATE records SET payload=? WHERE id=?',(system.json.dumps(data),row['id']))
        report=self.report(prop='')['future'][0];self.assertEqual(report['available'],10)
