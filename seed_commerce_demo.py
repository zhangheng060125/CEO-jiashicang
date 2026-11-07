"""Senhuo Select demo only. Does not create real transactions or copy hotel revenue."""
from datetime import date,timedelta
import server as s


def seed():
    with s.db() as c:
        if c.execute("SELECT 1 FROM records WHERE dataset='demo' AND kind='commerce_product' AND external_id='DEMO-YX-OWN'").fetchone():return
        prop='youxuan';actor={'username':'森活优选模拟初始化','role':'admin','properties':['*'],'demo':True}
        today=date.fromisoformat(s.TODAY())
        def put(kind,ext,data):return s.save_record(c,actor,kind,'demo',prop,ext,data)
        p=next(r for r in s.records(c,'demo','property') if r['property_id']==prop)
        s.save_record(c,actor,'property','demo',prop,p['external_id'],{**p['data'],'status':'open','note':'森活优选模拟场景，交易、商品和合作条款均为演示，不代表真实实绩'},p['id'],p['version'])
        catalog=[('OWN','演示·自营文旅礼盒','self','physical',True,'文创伴手礼'),('JOINT','演示·联营地方特产','joint','physical',False,'地方特产'),('AFF','演示·合作度假体验券','affiliate','voucher',False,'旅游权益'),('RETAIL','演示·门店零售茶礼','retail','physical',True,'茶与生活'),('JOINT-GROSS','演示·联名自提产品','joint','physical',False,'联营合作'),('OTHER','演示·待确认服务产品','other','service',False,'拓展服务')]
        for code,name,mode,typ,owned,category in catalog:
            put('commerce_product','DEMO-YX-'+code,dict(code='DEMO-YX-'+code,name=name,mode=mode,product_type=typ,supplier='演示合作方' if mode in ['joint','affiliate'] else '',category=category,owned_stock=owned,active=True,unit='份' if typ!='physical' else '件',reference_price=None,owner='演示优选运营',note='仅演示商品与模式，不代表实际售价或合同'))
        originals={(r['data']['order_no']):r['data'] for r in s.records(c,'demo','order',['bhl'])}
        for offset in range(-29,1):
            day=(today+timedelta(days=offset)).isoformat()
            for code,mode,recognition,collector,delivery,amount,fee in [
                ('OWN','self','gross','platform','shipping',256,256),
                ('JOINT','joint','net','platform','shipping',398,59.7),
                ('AFF','affiliate','net','supplier','redeem',298,44.7),
                ('RETAIL','retail','gross','platform','pickup',237,237),
                ('JOINT-GROSS','joint','gross','platform','pickup',132,132)]:
                no=f'DEMO-YX-{code}-{day}';old_park='DEMO-bhl-'+day+'-0' if offset%7==0 else ''
                park=code=='AFF' and old_park in originals
                qty=1 if park else 2
                if park:amount=originals[old_park]['booking_amount'];fee=round(amount*.08,2)
                paid_traffic=code in ['OWN','JOINT'];deferred=code=='OWN' and offset==0
                put('commerce_line',no,dict(order_no=no,line_no='1',order_date=day,product_code='DEMO-YX-'+code,mode=mode,channel='douyin' if paid_traffic else 'miniapp' if code=='AFF' else 'private',traffic='paid' if paid_traffic else 'organic',campaign_code='DEMO-YX-ADS' if paid_traffic else '',quantity=qty,cancelled_quantity=0,amount=amount,recognition=recognition,collector=collector,delivery=delivery,status='confirmed' if deferred else 'completed',ship_due=day if delivery=='shipping' else '',settle_due=(date.fromisoformat(day)+timedelta(days=7)).isoformat(),cost_complete=not deferred,park_property='bhl' if park else '',park_order=old_park if park else '',customer_code='DEMO-YX-C'+code+'-'+str(offset%12),owner='演示优选负责人',note='模拟合同口径与订单，不是实际合作条款'))
                def event(suffix,typ,event_day,amount,quantity=0,recognized=None,supplier=None,location='',fee_amount=None):
                    return put('commerce_event',no+'-'+suffix,dict(order_no=no,line_no='1',day=event_day,type=typ,amount=amount,quantity=quantity,recognized_amount=recognized,supplier_amount=supplier,fee_amount=fee_amount,funds_location=location,source_ref=no+'-'+suffix,owner='演示优选财务',note='模拟支付、交付或结算事件'))
                location='supplier' if collector=='supplier' else 'channel' if delivery=='shipping' else 'bank'
                event('PAY','payment',day,amount,location=location)
                if deferred:continue
                if delivery=='shipping':event('SHIP','shipped',day,0,quantity=qty)
                event('FULFILL','fulfilled',day,amount,quantity=qty,recognized=fee,supplier=round(amount-fee,2) if recognition=='net' and collector=='platform' else 0)
                if recognition=='gross':
                    cost=round(amount*.58,2)
                    put('commerce_cost',no+'-COGS',dict(day=day,category='goods',amount=cost,order_no=no,line_no='1',source_ref=no+'-COGS',owner='演示财务',note='模拟实际销售商品成本，不是采购入库全额'))
                    event('ACCRUE','supplier_accrual',day,cost)
                    if offset<=-3:event('SUPPLY-PAY','supplier_payout',(today+timedelta(days=offset+3)).isoformat(),cost,location='bank')
                if delivery=='shipping':
                    put('commerce_cost',no+'-LOGISTICS',dict(day=day,category='logistics',amount=8,order_no=no,line_no='1',source_ref=no+'-LOGISTICS',owner='演示财务'))
                    if offset<=-2:event('SETTLE','settlement',(today+timedelta(days=offset+2)).isoformat(),round(amount*.98,2),location='bank',fee_amount=round(amount*.02,2))
                if recognition=='net' and collector=='platform' and offset<=-3:event('SUPPLY-PAY','supplier_payout',(today+timedelta(days=offset+3)).isoformat(),round(amount-fee,2),location='bank')
                if collector=='supplier' and offset<=-5:event('COMM-RECEIPT','commission_received',(today+timedelta(days=offset+5)).isoformat(),round(fee*.6,2),location='bank')
                if code=='OWN' and offset==-7:event('REFUND','refund',(today-timedelta(days=1)).isoformat(),128,quantity=1,recognized=128,supplier=0,location='bank')
                if code=='JOINT' and offset==-8:event('REFUND','refund',(today-timedelta(days=1)).isoformat(),amount,quantity=qty,recognized=fee,supplier=round(amount-fee,2),location='bank')
                if code=='AFF' and offset==-9:event('REFUND','refund',(today-timedelta(days=1)).isoformat(),amount,quantity=qty,recognized=fee,supplier=0,location='supplier')
            put('commerce_cost','DEMO-YX-ADS-'+day,dict(day=day,category='advertising',amount=100,campaign_code='DEMO-YX-ADS',source_ref='DEMO-YX-ADS-'+day,owner='演示财务',note='模拟活动花费，不再重复作为订单直接广告费录入'))
            s.save_record(c,actor,'coverage','demo',prop,'DEMO-YX-COVER-'+day,dict(day=day,complete=True,owner='演示财务',note='模拟平台费用完整性确认'))
            for channel,uv,payers in [('douyin',240,2),('miniapp',80,1),('private',100,2)]:
                put('commerce_traffic','DEMO-YX-UV-'+day+'-'+channel,dict(day=day,channel=channel,level='platform',product_code='',visitors=uv,paying_visitors=payers,impressions=uv*5,clicks=uv*2,observed_through=day,cohort_complete=True,source_ref='DEMO-UV-'+day+'-'+channel,owner='演示运营',note='当日渠道访问批次，不冒充跨日独立访客'))
        for code,qty in [('OWN',35),('RETAIL',0)]:
            put('commerce_stock','DEMO-YX-STOCK-'+code,dict(day=s.TODAY(),product_code='DEMO-YX-'+code,warehouse='DEMO-WH',on_hand=qty,reserved=5 if qty else 0,unusable=0,last_outbound=s.TODAY(),source_ref='DEMO-STOCK-'+code,owner='演示库管'))
        put('commerce_line','DEMO-YX-PENDING',dict(order_no='DEMO-YX-PENDING',line_no='1',order_date=s.TODAY(),product_code='DEMO-YX-OTHER',mode='other',channel='unknown',traffic='unknown',quantity=1,cancelled_quantity=0,amount=200,recognition='unconfirmed',collector='platform',delivery='service',status='confirmed',cost_complete=False,owner='演示优选运营',note='展示合同待确认，未履约不编造收入'))
        s.check_relations(c,'demo')
    print('Senhuo Select initialized in DEMO only; park accounting and actual transactions untouched.')


if __name__=='__main__':seed()
