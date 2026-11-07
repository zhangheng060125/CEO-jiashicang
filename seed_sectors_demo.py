"""Professional sector examples; exclusively synthetic, idempotent, DEMO dataset only."""
from datetime import date, timedelta
import json
import server as s


def seed():
    with s.db() as c:
        if c.execute("SELECT 1 FROM records WHERE dataset='demo' AND external_id='SECTOR6-MARKER'").fetchone():return
        actor={'username':'分业态演示初始化','role':'admin','properties':['*'],'demo':True}
        today=date.fromisoformat(s.TODAY())
        def put(kind,prop,ext,data):return s.save_record(c,actor,kind,'demo',prop,ext,data)
        for prop in ['bhcs','jtxy','water','spa']:
            row=next(r for r in s.records(c,'demo','property') if r['property_id']==prop)
            data={**row['data'],'status':'seasonal' if prop=='water' else 'open'}
            s.save_record(c,actor,'property','demo',prop,row['external_id'],data,row['id'],row['version'])
        def sale(prop,business,day,amount,guests,guest_type='not_applicable',suffix=''):
            no=f'DEMO-SECTOR-{prop}-{day}{suffix}'
            put('order',prop,no,dict(order_no=no,order_date=day,checkin=day,checkout=day,kind=business,status='completed',booking_amount=amount,channel='offline',traffic='organic',customer_code='',owner='演示业务负责人'))
            put('fulfillment',prop,no+'-RIGHT',dict(order_no=no,day=day,business=business,amount=amount,room_nights=0,included=False,guest_type=guest_type,guests=guests))
            put('payment',prop,no+'-PAY',dict(order_no=no,day=day,type='collection',destination='bank',amount=amount,revenue_reversal=0))
        for offset in range(-29,1):
            d=today+timedelta(days=offset);day=d.isoformat()
            for prop in ['bhcs','jtxy']:
                people=40+offset%9;amount=people*(88 if prop=='bhcs' else 108)
                sale(prop,'dining',day,amount,people,'walkin')
                if d.weekday()>=5:sale(prop,'dining',day,6000,60,'banquet','-BANQUET')
                put('business_day',prop,'SECTOR6-DINING-'+day,dict(day=day,business='dining',is_open=True,complete=True,available_tables=12,meal_periods=2,served_tables=24+offset%5,waste_cost=35+offset%8,labor_hours=64,owner='演示餐饮经理',source_ref='DEMO-POS-'+day,note='模拟开台与食材损耗；不是实际经营实绩'))
                food=round((amount+(6000 if d.weekday()>=5 else 0))*.32,2)
                put('cost',prop,'SECTOR6-FOOD-'+day,dict(day=day,category='food',amount=food,scope='park',business='dining',note='模拟实际耗用（含损耗），不是采购入库金额'))
                put('coverage',prop,'SECTOR6-COVER-'+day,dict(day=day,complete=True,owner='演示财务',note='仅为模拟财务完整性确认'))
            # Attached breakfast and SPA departments also need their own operating calendar.
            for prop in ['bhl','jtw']:
                put('business_day',prop,'SECTOR6-ATTACHED-DINING-'+day,dict(day=day,business='dining',is_open=True,complete=True,available_tables=20,meal_periods=1,served_tables=18+offset%6,waste_cost=20,labor_hours=40,owner='演示早餐主管',source_ref='DEMO-BREAKFAST-'+day))
                put('cost',prop,'SECTOR6-BREAKFAST-FOOD-'+day,dict(day=day,category='food',amount=450,scope='park',business='dining',note='模拟赠送早餐实际食材耗用，不新增早餐收入'))
                put('business_day',prop,'SECTOR6-ATTACHED-SPA-'+day,dict(day=day,business='spa',is_open=True,complete=True,visitors=50,appointments=40,completed_appointments=32,available_minutes=2400,used_minutes=1440,labor_hours=48,owner='演示温泉主管',source_ref='DEMO-HOTEL-SPA-'+day))
            opened=d.weekday() not in [1,2]
            people=120+offset%35 if opened else 0
            put('business_day','water','SECTOR6-WATER-'+day,dict(day=day,business='water',is_open=opened,complete=True,visitors=people,daily_capacity=500 if opened else 0,safety_incidents=0,labor_hours=72 if opened else 0,owner='演示游乐经理',source_ref='DEMO-GATE-'+day,note='模拟每周二三停业；真实日历和日承载需负责人确认'))
            if opened:
                sale('water','water',day,people*98,people)
                put('coverage','water','SECTOR6-COVER-'+day,dict(day=day,complete=True,owner='演示财务',note='模拟成本确认'))
                put('cost','water','SECTOR6-WATER-COST-'+day,dict(day=day,category='utilities',amount=2000,scope='park',business='water',note='模拟水世界耗用'))
            sale('spa','spa',day,4200,24)
            put('business_day','spa','SECTOR6-SPA-'+day,dict(day=day,business='spa',is_open=True,complete=True,visitors=24,appointments=20,completed_appointments=16,available_minutes=1920,used_minutes=1080,labor_hours=32,owner='演示SPA经理',source_ref='DEMO-APPOINTMENT-'+day))
            put('coverage','spa','SECTOR6-COVER-'+day,dict(day=day,complete=True,owner='演示财务',note='模拟成本确认'))
            put('cost','spa','SECTOR6-SPA-COST-'+day,dict(day=day,category='supplies',amount=700,scope='park',business='spa',note='模拟耗材'))
        put('business_day','bhcs','SECTOR6-MARKER',dict(day=(today-timedelta(days=30)).isoformat(),business='dining',is_open=False,complete=True,owner='演示初始化',note='幂等标记，仅模拟数据'))
        s.check_relations(c,'demo')
    print('Sector examples initialized in DEMO only; actual ledgers and configuration untouched.')


if __name__=='__main__':seed()
