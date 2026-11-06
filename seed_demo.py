"""Synthetic examples only. Never writes actual business records."""
from datetime import date,timedelta
import json
import server as s

def seed():
 with s.db() as c:
  if c.execute("SELECT 1 FROM records WHERE dataset='demo' AND kind='order'").fetchone():return
  def put(kind,prop,ext,data):
   clean=s.validate(kind,data)
   c.execute('INSERT INTO records(kind,dataset,property_id,external_id,payload,updated_at) VALUES(?,?,?,?,?,?)',(kind,'demo',prop,ext,json.dumps(clean,ensure_ascii=False),s.NOW()))
  today=date.fromisoformat(s.TODAY())
  for row in s.records(c,'demo','property'):
   d=row['data'];d['status']='open' if d['code'] in ['bhl','jtw'] else 'planning'
   d['note']='演示场景配置，非真实房量或开放状态。'+d['note']
   c.execute('UPDATE records SET payload=? WHERE id=?',(json.dumps(d,ensure_ascii=False),row['id']))
  for prop,rooms,rate in [('bhl',40,1200),('jtw',32,760)]:
   put('contract',prop,'DEMO-CONTRACT',dict(code='DEMO-CONTRACT',start=(today-timedelta(days=365)).isoformat(),end=(today+timedelta(days=365)).isoformat(),rate=.08,basis='fulfilled',beneficiary='operator',settlement_days=7,note='模拟8%佣金，不代表实际合同'))
   for offset in range(-59,90):
    d=today+timedelta(days=offset);day=d.isoformat()
    put('inventory',prop,'INV-'+day,dict(day=day,room_type='演示标准房',physical=rooms,out_of_service=2,available=rooms-2,locked=1,voucher_commitment=8,is_open=True,day_type='weekend' if d.weekday()>4 else 'workday',rate=rate))
    if offset<=0:
     put('coverage',prop,'COV-'+day,dict(day=day,complete=offset!=-3,owner='演示财务',note='模拟成本确认；最近第3日前故意留缺失例'))
     put('cost',prop,'COST-'+day,dict(day=day,category='payroll',amount=rooms*80,scope='park',order_no='',note='演示日分摊工资'))
     put('campaign',prop,'LIVE-'+day,dict(code='LIVE-'+day,day=day,channel='douyin',format='live',traffic='paid',impressions=2200+(offset%7)*170,viewers=800,consultations=35,spend=500,owner='演示运营'))
    if offset < -29 or offset > 20:continue
    for j,ch in enumerate(['douyin','ctrip','private']):
     if offset>0 and j==2:continue
     no=f'DEMO-{prop}-{day}-{j}';room_count=(8+offset%4) if prop=='bhl' else 6+offset%3
     amount=room_count*rate;old=offset<=0
     put('order',prop,no,dict(order_no=no,order_date=(d-timedelta(days=6)).isoformat(),checkin=day,checkout=(d+timedelta(days=1)).isoformat(),kind='stay',status='completed' if old else 'confirmed',booking_amount=amount,customer_code=f'DEMO-C{j}-{offset%8}',channel=ch,discovery=ch if j!=1 else 'unknown',assist='unknown',traffic='paid' if j==0 else 'organic',campaign_code='LIVE-'+day if j==0 and old else '',contract_code='DEMO-CONTRACT' if j==0 else '',owner='演示店长'))
     put('reservation',prop,no+'-RS',dict(order_no=no,day=day,room_type='演示标准房',rooms=room_count,status='confirmed'))
     put('payment',prop,no+'-PAY',dict(order_no=no,day=(d-timedelta(days=5)).isoformat(),type='collection',destination='bank' if ch=='private' else 'platform',amount=amount,revenue_reversal=0,due_date=(d+timedelta(days=7)).isoformat()))
     if old:
      put('fulfillment',prop,no+'-ROOM',dict(order_no=no,day=day,business='room',amount=amount*.9,room_nights=room_count,included=False,guest_type='not_applicable',guests=0))
      put('fulfillment',prop,no+'-SPA',dict(order_no=no,day=day,business='spa',amount=amount*.1,room_nights=0,included=False,guest_type='not_applicable',guests=room_count*2))
      put('fulfillment',prop,no+'-BREAKFAST',dict(order_no=no,day=day,business='dining',amount=0,room_nights=0,included=True,guest_type='resident',guests=room_count*2))
      put('cost',prop,no+'-COST',dict(day=day,category='supplies',amount=room_count*110,scope='park',order_no=no,note='演示客用品与变动成本'))
      if offset<-8 and ch!='private':put('payment',prop,no+'-SETTLE',dict(order_no=no,day=(d+timedelta(days=7)).isoformat(),type='settlement',destination='bank',amount=amount,revenue_reversal=0,due_date=''))
      if offset==-2 and j==0:put('payment',prop,no+'-REFUND',dict(order_no=no,day=day,type='refund',destination='platform',amount=rate,revenue_reversal=rate,due_date=''))
   put('issue',prop,'ISSUE-1',dict(day=s.TODAY(),department='kitchen',title='演示：厨房留样记录缺失',severity='redline',order_no='',evidence='模拟SOP检查编号 DEMO-SOP-01，非实际问题',owner='演示餐饮负责人',due_date=s.TODAY(),status='open',remediation='',review_result='',reviewer=''))
   put('target',prop,'BUDGET',dict(start=(today-timedelta(days=29)).isoformat(),end=today.isoformat(),channel='',scenario='budget',revenue=900000,cost=500000,occupancy=.7,owner='演示总经理'))
   put('customer',prop,'DEMO-CUSTOMER',dict(code='DEMO-C0-1',phone_last4='1234',day=s.TODAY(),owner='演示客服',response_minutes=8,reason='',status='converted'))
  s.check_relations(c,'demo')
 print('Synthetic demo seeded; actual records unchanged.')
if __name__=='__main__':seed()
