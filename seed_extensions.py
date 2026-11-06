"""Idempotent additions to the isolated demonstration dataset; never touches actual."""
from datetime import date,timedelta
import server as s

def seed():
 with s.db() as c:
  if c.execute("SELECT 1 FROM records WHERE dataset='demo' AND kind='product' AND external_id='SEED2-PRODUCT'").fetchone():return
  u={'username':'demo seed v2','role':'admin','properties':['*'],'demo':True};prop='bhl';today=date.fromisoformat(s.TODAY());viewday=(today-timedelta(days=4)).isoformat();useday=(today-timedelta(days=2)).isoformat()
  def put(kind,ext,data):return s.save_record(c,u,kind,'demo',prop,ext,data)
  put('product','SEED2-PRODUCT',dict(code='DEMO-SPA',name='演示·芳疗体验券',business='spa',active=True,unit='次',reference_price=200,owner='演示产品负责人'))
  put('campaign','SEED2-CAMPAIGN',dict(code='DEMO-COHORT',day=viewday,channel='douyin',format='live',traffic='organic',impressions=5000,viewers=1800,consultations=30,spend=0,owner='演示直播负责人'))
  for who in ['DEMO-COHORT-A','DEMO-COHORT-B']:
   put('touchpoint','SEED2-VIEW-'+who,dict(day=viewday,customer_code=who,campaign_code='DEMO-COHORT',stage='view',evidence='演示匿名事件，不代表平台真实流量'))
  put('touchpoint','SEED2-CONSULT',dict(day=viewday,customer_code='DEMO-COHORT-A',campaign_code='DEMO-COHORT',stage='consult',evidence='演示咨询事件'))
  put('order','SEED2-ORDER',dict(order_no='DEMO-VOUCHER-2',order_date=viewday,checkin=useday,checkout=useday,kind='voucher',status='confirmed',booking_amount=600,customer_code='DEMO-COHORT-A',channel='douyin',discovery='douyin',assist='unknown',traffic='organic',campaign_code='DEMO-COHORT',owner='演示客户负责人'))
  put('payment','SEED2-PAY',dict(order_no='DEMO-VOUCHER-2',day=viewday,type='collection',destination='bank',amount=600,revenue_reversal=0))
  put('entitlement','SEED2-RIGHT',dict(code='DEMO-RIGHT-2',order_no='DEMO-VOUCHER-2',product_code='DEMO-SPA',business='spa',quantity=3,cancelled_units=0,allocated_amount=600,expires_on=(today+timedelta(days=60)).isoformat(),note='演示3次券；未核销收款不确认为收入'))
  put('fulfillment','SEED2-USE',dict(order_no='DEMO-VOUCHER-2',day=useday,business='spa',amount=200,room_nights=0,included=False,guest_type='not_applicable',guests=1,product_code='DEMO-SPA',entitlement_code='DEMO-RIGHT-2',redeemed_units=1))
  put('cost','SEED2-COST',dict(day=useday,category='supplies',amount=50,scope='park',order_no='DEMO-VOUCHER-2',business='spa',product_code='DEMO-SPA',note='演示显式产品成本'))
  put('sop_item','SEED2-SOP',dict(code='DEMO-SOP-KITCHEN',department='kitchen',title='演示·厨房留样检查',standard='留样时间、标签、温度均符合酒店确认的标准',redline=True,active=True))
  put('sop_check','SEED2-CHECK',dict(day=useday,item_code='DEMO-SOP-KITCHEN',result='fail',evidence='演示不合格记录，非实际卫生问题',owner='演示厨房负责人',due_date=s.TODAY()))
  put('review','SEED2-REVIEW',dict(day=useday,channel='演示点评数据',order_no='DEMO-VOUCHER-2',rating=4,category='service',content='演示评价：希望预约响应更快。',owner='演示客户负责人',response='演示回复：已调整排班。',status='responded'))
  put('alert_rule','SEED2-RULE',dict(code='booking7',channel='',enabled=True,threshold=.55,severity='major',owner='演示收益负责人',deadline_days=2))
  s.check_relations(c,'demo')
 print('Extended demo initialized; actual business records unchanged.')
if __name__=='__main__':seed()
