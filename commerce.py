"""Senhuo Select: separate commerce operations, accounting facts and source evidence."""
from datetime import date,timedelta

MODES={'self':'自营产品','joint':'联营产品','affiliate':'电商带货','retail':'零售产品','other':'其他合作'}
CHANNELS=['unknown','douyin','xiaohongshu','wechat','miniapp','private','taobao','jd','pdd','offline','other']
FINANCE={'admin','finance'}
EVENTS=['payment','refund','shipped','fulfilled','settlement','commission_received','commission_return','supplier_accrual','supplier_payout','supplier_credit']
FIN_EVENTS=set(EVENTS)-{'shipped','fulfilled'}
KINDS={'commerce_product','commerce_line','commerce_event','commerce_cost','commerce_traffic','commerce_stock'}
PRIVATE_EVENT={'recognized_amount','supplier_amount','fee_amount','funds_location'}


def schemas(f):
    return {
      'commerce_product':dict(label='森活优选商品与合作目录',fields={
        'code':f('SKU/产品代码'),'name':f('产品名称'),'mode':f('经营模式','select',True,list(MODES)),
        'product_type':f('商品形态','select',True,['physical','voucher','service','other']),
        'supplier':f('供应商/合作方','text',False),'category':f('产品品类','text',False),
        'owned_stock':f('平台承担自有库存','bool'),'active':f('在售','bool'),
        'unit':f('单位'),'reference_price':f('参考售价（非实际成交价）','number',False),
        'owner':f('产品负责人'),'note':f('合作合同及业务说明','text',False)}),
      'commerce_line':dict(label='森活优选订单行',fields={
        'order_no':f('平台订单号'),'line_no':f('订单行编号'),'order_date':f('下单日期','date'),
        'product_code':f('SKU/产品代码'),'mode':f('成交时经营模式','select',True,list(MODES)),
        'channel':f('成交渠道','select',True,CHANNELS),'traffic':f('流量属性','select',True,['unknown','organic','paid']),
        'campaign_code':f('可核对的投放活动代码','text',False),'quantity':f('成交数量','integer'),
        'cancelled_quantity':f('已取消未履约数量（非实物退货）','integer',False),
        'amount':f('本行优惠后交易额（退款前）','number'),
        'recognition':f('合同收入确认方式','select',True,['unconfirmed','gross','net']),
        'collector':f('客户款收取方','select',True,['unconfirmed','platform','supplier']),
        'delivery':f('实际履约方式','select',True,['shipping','pickup','redeem','service']),
        'status':f('订单状态','select',True,['confirmed','completed','cancelled']),
        'ship_due':f('约定最晚发货日','date',False),'settle_due':f('约定结算/佣金到期日','date',False),
        'cost_complete':f('本行直接成本已核对（财务确认）','bool',False),
        'park_property':f('关联园区项目代码（可空）','text',False),
        'park_order':f('关联园区订单号（可空）','text',False),
        'customer_code':f('匿名客户编号','text',False),'owner':f('跟进负责人'),
        'note':f('合同与订单口径','text',False)}),
      'commerce_event':dict(label='森活优选支付履约与结算事件',fields={
        'order_no':f('平台订单号'),'line_no':f('订单行编号'),'day':f('实际发生日','date'),
        'type':f('事件类型','select',True,EVENTS),'amount':f('本次交易/资金金额（发货填0）','number'),
        'quantity':f('本次发货/履约/退回商品或权益数量','integer',False),
        'recognized_amount':f('本次确认/冲回的平台收入（净额须核实）','number',False),
        'supplier_amount':f('本次增加/冲回代收合作方款','number',False),
        'fee_amount':f('本次结算中平台扣费（不重复录成本）','number',False),
        'funds_location':f('资金位置','select',False,['channel','bank','supplier']),
        'source_ref':f('原支付/物流/核销/结算凭证编号'),
        'owner':f('记录负责人'),'note':f('原始依据','text',False)}),
      'commerce_cost':dict(label='森活优选成本与投放',fields={
        'day':f('费用归属日','date'),'category':f('成本类别','select',True,['goods','logistics','packaging','advertising','creator','service','after_sale','other']),
        'amount':f('成本金额（未知留空）','number',False),
        'order_no':f('关联订单（空为未分摊公共费用）','text',False),
        'line_no':f('关联订单行（与订单号同时填）','text',False),
        'campaign_code':f('广告活动代码（用于可核对ROAS）','text',False),
        'source_ref':f('成本/投放原始凭证编号'),'owner':f('核对负责人'),
        'note':f('耗用及分摊依据；结算扣费不重复录入','text',False)}),
      'commerce_traffic':dict(label='森活优选流量与访问批次',fields={
        'day':f('访问批次日期','date'),'channel':f('渠道','select',True,CHANNELS),
        'level':f('统计层级','select',True,['platform','product']),
        'product_code':f('产品级必须填SKU（平台级留空）','text',False),
        'visitors':f('该日该渠道去重访客UV','integer',False),
        'paying_visitors':f('同批访客中已支付人数','integer',False),
        'impressions':f('曝光次数','integer',False),'clicks':f('点击次数','integer',False),
        'observed_through':f('归因观察截止日','date'),'cohort_complete':f('本批归因窗口已核对完整','bool'),
        'source_ref':f('原平台报表/批次编号'),'owner':f('核对负责人'),'note':f('归因窗口与去重口径','text',False)}),
      'commerce_stock':dict(label='森活优选自有库存快照',fields={
        'day':f('快照日期','date'),'product_code':f('SKU/产品代码'),'warehouse':f('仓库/门店代码'),
        'on_hand':f('实物库存数量','integer'),'reserved':f('已锁定数量','integer'),
        'unusable':f('残损/不可售数量（不含锁定）','integer'),
        'last_outbound':f('最近实际出库日','date',False),'source_ref':f('库存系统/盘点编号'),
        'owner':f('盘点负责人'),'note':f('库存口径','text',False)}),
    }


def validate(kind,d):
    if kind=='commerce_line':
        if not d['quantity']:raise ValueError('订单行数量必须大于0')
        if (d.get('cancelled_quantity') or 0)>d['quantity']:raise ValueError('取消未履约数量不能超过成交数量')
        if bool(d['park_property'])!=bool(d['park_order']):raise ValueError('关联园区项目和订单号须同时填写')
        if d['mode']=='affiliate' and d['recognition']=='gross':raise ValueError('带货订单不能把商家成交额全额确认为平台收入')
        if d['recognition']=='gross' and d['collector']=='supplier':raise ValueError('全额销售与商家直接收款口径不一致，请财务核对合同')
        for key in ['ship_due','settle_due']:
            if d[key] and d[key]<d['order_date']:raise ValueError('约定日期不能早于下单日')
    if kind=='commerce_event':
        typ=d['type'];qty=d.get('quantity') or 0
        if typ in ['shipped','fulfilled'] and not qty:raise ValueError('发货和履约事件必须有实际数量')
        if typ=='shipped' and d['amount']!=0:raise ValueError('发货仅记录数量，不确认交易或收入金额')
        if typ not in ['fulfilled','refund'] and any(d.get(k) not in (None,0) for k in ['recognized_amount','supplier_amount']):raise ValueError('只有履约/退款可以确认或冲回收入及代收合作方款')
        if typ!='settlement' and d.get('fee_amount') not in (None,0):raise ValueError('结算扣费只填写在结算到账事件中')
        if typ not in ['shipped','fulfilled','refund'] and qty:raise ValueError('资金事件不能增加发货或履约数量')
        if (d.get('recognized_amount') or 0)+(d.get('supplier_amount') or 0)>d['amount']+.001:raise ValueError('平台收入加代收合作方款不能超过本次履约/退款交易额')
    if kind=='commerce_cost' and bool(d['order_no'])!=bool(d['line_no']):raise ValueError('关联费用须同时填写订单号和订单行')
    if kind=='commerce_traffic':
        if (d['level']=='product')!=bool(d['product_code']):raise ValueError('平台级和产品级流量必须分开，产品级填写SKU')
        if d['observed_through']<d['day']:raise ValueError('观察截止不能早于访问批次日')
        if d.get('visitors') is not None and d.get('paying_visitors') is not None and d['paying_visitors']>d['visitors']:raise ValueError('同批支付人数不能大于该批访客数')
    if kind=='commerce_stock':
        if d['reserved']+d['unusable']>d['on_hand']:raise ValueError('锁定加不可售数量不能超过实物库存')
        if d['last_outbound'] and d['last_outbound']>d['day']:raise ValueError('最近出库日不能晚于库存快照日')
    if kind=='commerce_product' and d['owned_stock'] and d['product_type']!='physical':raise ValueError('券和服务权益不作为自有实物库存')
    if kind=='commerce_product' and d['mode']=='affiliate' and d['owned_stock']:raise ValueError('带货商家库存不能登记为平台自有库存')


def income(event,line):
    if event['type'] not in ['fulfilled','refund']:return 0
    if line['recognition']=='unconfirmed':return None
    if event['type']=='fulfilled' and line['recognition']=='gross':return event['amount']
    return event.get('recognized_amount')


def check_relations(index):
    for (prop,kind),items in index.items():
        if kind not in KINDS:continue
        group={k:v for (p,k),v in index.items() if p==prop}
        if group.get('property',[{}])[0].get('business')!='commerce':raise ValueError('森活优选数据必须归属独立的线上平台项目')
        products={x['code']:x for x in group.get('commerce_product',[])}
        lines={(x['order_no'],x['line_no']):x for x in group.get('commerce_line',[])}
        natural={'commerce_product':lambda x:x['code'],'commerce_line':lambda x:(x['order_no'],x['line_no']),
                 'commerce_event':lambda x:(x['order_no'],x['line_no'],x['type'],x['source_ref']),
                 'commerce_cost':lambda x:(x['source_ref'],x['category'],x['order_no'],x['line_no']),
                 'commerce_traffic':lambda x:(x['day'],x['channel'],x['level'],x['product_code']),
                 'commerce_stock':lambda x:(x['day'],x['product_code'],x['warehouse'])}
        if kind in natural:
            keys=[natural[kind](x) for x in items]
            if len(keys)!=len(set(keys)):raise ValueError('森活优选的业务编号/日报/库存快照重复，请编辑原记录')
        for x in items:
            if x.get('product_code') and x['product_code'] not in products:raise ValueError('森活优选SKU不存在')
            if kind=='commerce_stock' and not products[x['product_code']]['owned_stock']:raise ValueError('商家库存不作为平台自有库存，请核对库存归属')
            if kind in ['commerce_event','commerce_cost'] and x.get('order_no'):
                line=lines.get((x['order_no'],x['line_no']))
                if not line:raise ValueError('森活优选关联订单行不存在')
                if x['day']<line['order_date']:raise ValueError('事件/费用日期不能早于关联订单日')
            if kind=='commerce_line':
                if x['park_order'] and not any(o['order_no']==x['park_order'] for o in index.get((x['park_property'],'order'),[])):raise ValueError('关联园区原订单不存在')
        if kind!='commerce_line':continue
        events=group.get('commerce_event',[])
        for key,line in lines.items():
            es=sorted([e for e in events if (e['order_no'],e['line_no'])==key],key=lambda e:(e['day'],e.get('_id',0)))
            paid=refunded=shipped=fulfilled=fulfilled_amount=recognized=supplier=settled=commission_cash=supplier_paid=accrued=credited=returned_qty=0
            processed=[]
            for e in es:
                processed.append(e)
                typ=e['type'];amount=e['amount'];qty=e.get('quantity') or 0
                known_income=income(e,line)
                if typ in ['payment','refund']:
                    if not e.get('funds_location'):raise ValueError('收退款必须记录资金位置')
                    if line['collector']=='unconfirmed':raise ValueError('请先确认客户款的实际收取方')
                    if (line['collector']=='supplier')!=(e['funds_location']=='supplier'):raise ValueError('收退款资金位置与订单收款方不一致')
                if typ=='payment':paid+=amount
                if typ=='refund':
                    refunded+=amount;returned_qty+=qty
                    if known_income is not None:
                        if known_income>recognized+.01:raise ValueError('退款收入冲回超过当时已确认的平台收入')
                        recognized-=known_income
                    if (e.get('supplier_amount') or 0)>supplier+.01:raise ValueError('退款合作方冲回超过已登记的代收合作方款')
                    supplier-=e.get('supplier_amount') or 0
                if typ=='shipped':
                    if line['delivery']!='shipping':raise ValueError('自提/核销/服务订单不使用物流发货事件')
                    shipped+=qty
                if typ=='fulfilled':
                    if line['status']=='cancelled':raise ValueError('已取消订单不能新增实际履约')
                    fulfilled+=qty;fulfilled_amount+=amount
                    if line['recognition']=='gross' and e.get('recognized_amount') not in [None,amount]:raise ValueError('全额确认的履约收入应等于实际交付交易额')
                    if known_income is not None:recognized+=known_income
                    if line['recognition']=='net' and line['collector']=='platform' and known_income is not None:
                        if e.get('supplier_amount') is None or abs(known_income+e['supplier_amount']-amount)>.01:raise ValueError('净额代收须明确平台收入与合作方本金分配')
                    if line['collector']=='supplier' and (e.get('supplier_amount') or 0):raise ValueError('商家直接收款不形成平台代收本金')
                    supplier+=e.get('supplier_amount') or 0
                if typ=='settlement':
                    if line['collector']!='platform' or e['funds_location']!='bank':raise ValueError('结算到账仅用于平台代收转入本方银行')
                    settled+=amount+(e.get('fee_amount') or 0)
                    channel_net=sum(x['amount']*(1 if x['type']=='payment' else -1) for x in processed if x['type'] in ['payment','refund'] and x['funds_location']=='channel')
                    if settled>channel_net+.01:raise ValueError('结算本金及扣费超过渠道净收款')
                if typ in ['commission_received','commission_return']:
                    if line['collector']!='supplier' or line['recognition']!='net' or e['funds_location']!='bank':raise ValueError('佣金收退只用于商家直收、净额确认的银行资金')
                    commission_cash+=amount*(1 if typ=='commission_received' else -1)
                    if typ=='commission_received' and commission_cash>recognized+.01:raise ValueError('佣金到账超过当时已确认佣金，预付款不能当已履约佣金')
                    if commission_cash<-.01:raise ValueError('退回佣金超过已收到金额')
                if typ in ['supplier_accrual','supplier_credit']:
                    if line['recognition']!='gross':raise ValueError('净额代收合作方款来自履约分配，不可再重复登记应付')
                    if typ=='supplier_accrual':accrued+=amount
                    else:credited+=amount
                    if credited>accrued+.01:raise ValueError('采购应付冲回超过已登记应付')
                if typ=='supplier_payout':
                    if e['funds_location']!='bank':raise ValueError('支付合作方款应记录银行资金')
                    supplier_paid+=amount
                    if supplier_paid>supplier+accrued-credited+.01:raise ValueError('支付合作方款超过当时已登记应付')
                if refunded>paid+.01 or paid>line['amount']+.01:raise ValueError('退款超过当时支付或累计支付超过订单行交易额')
                if shipped>line['quantity'] or fulfilled>line['quantity'] or returned_qty>fulfilled:raise ValueError('发货/履约/实物退货数量超过允许数量')
                if fulfilled+(line.get('cancelled_quantity') or 0)>line['quantity']:raise ValueError('履约加取消未履约数量不能超过成交数量')
                if line['delivery']=='shipping' and fulfilled>shipped:raise ValueError('物流商品未发货不能确认已交付')
                if fulfilled_amount>line['amount']+.01:raise ValueError('累计履约交易额超过订单行交易额')


def authorize(user,kind,data,previous=None):
    role=user['role'];previous=previous or {}
    if kind=='commerce_event' and role not in FINANCE and (data['type'] not in ['shipped','fulfilled'] or previous.get('type') in FIN_EVENTS):
        raise PermissionError('森活优选收退款和结算仅由财务确认，主管可记录发货与履约')
    if kind=='commerce_line' and role not in FINANCE:
        if data.get('cost_complete') is True and previous.get('cost_complete') is not True:raise PermissionError('只有财务可确认订单行直接成本完整')
        if data['recognition']!='unconfirmed' and data['recognition']!=previous.get('recognition'):raise PermissionError('合同全额/净额收入方式须由财务确认')
        if previous.get('cost_complete') is True:
            for key in ['product_code','mode','quantity','amount','recognition','collector','order_date']:
                if data[key]!=previous[key]:raise PermissionError('已核对的订单金额及核算口径须由财务更正')
            data['cost_complete']=True


def readable(rows,user):
    if user['role']!='operations':return rows
    out=[]
    for row in rows:
        if row['kind']=='commerce_event':
            if row['data']['type'] in FIN_EVENTS:continue
            row={**row,'data':{k:v for k,v in row['data'].items() if k not in PRIVATE_EVENT}}
        out.append(row)
    return out


def aggregate(records,start,end,asof):
    g={k:[{**r['data'],'_id':r['id'],'_property':r['property_id'],'_external':r['external_id'],'_updated':r['updated_at']} for r in records if r['kind']==k] for k in KINDS}
    lines={(x['_property'],x['order_no'],x['line_no']):x for x in g['commerce_line']}
    products={(x['_property'],x['code']):x for x in g['commerce_product']}
    key=lambda x:(x['_property'],x['order_no'],x['line_no'])
    inside=lambda x:start<=x.get('day',x.get('order_date',''))<=end
    total=lambda xs,field='amount':round(sum(x.get(field) or 0 for x in xs),2)
    ratio=lambda a,b:a/b if a is not None and b and b>0 else None
    es=[e for e in g['commerce_event'] if inside(e)];past=[e for e in g['commerce_event'] if e['day']<=end]
    costs=[x for x in g['commerce_cost'] if inside(x)]
    dated=[x for x in g['commerce_line'] if inside(x)]
    paid=[e for e in es if e['type']=='payment' and e['amount']>0];refunds=[e for e in es if e['type']=='refund']
    f=[e for e in es if e['type']=='fulfilled'];income_events=f+refunds
    def revenue(events):
        amounts=[income(e,lines[key(e)]) for e in events]
        return round(sum(a*(1 if e['type']=='fulfilled' else -1) for e,a in zip(events,amounts)),2) if amounts and all(a is not None for a in amounts) else None
    income_value=revenue(income_events)
    rows=[];fees=total([e for e in es if e['type']=='settlement'],'fee_amount')
    for lk,line in lines.items():
        le=[e for e in past if key(e)==lk];pe=[e for e in es if key(e)==lk]
        earned=revenue([e for e in le if e['type'] in ['fulfilled','refund']])
        all_paid=total([e for e in le if e['type']=='payment']);all_ref=total([e for e in le if e['type']=='refund'])
        channel=total([e for e in le if e['type']=='payment' and e['funds_location']=='channel'])-total([e for e in le if e['type']=='refund' and e['funds_location']=='channel'])-total([e for e in le if e['type']=='settlement'])-total([e for e in le if e['type']=='settlement'],'fee_amount')
        commission_received=total([e for e in le if e['type']=='commission_received'])-total([e for e in le if e['type']=='commission_return'])
        supplier_events=[e for e in le if e['type'] in ['fulfilled','refund']]
        supplier_unknown=line['recognition']=='net' and line['collector']=='platform' and any(e['supplier_amount'] is None for e in supplier_events)
        balance=(total([e for e in le if e['type']=='fulfilled'],'supplier_amount')-total([e for e in le if e['type']=='refund'],'supplier_amount')+total([e for e in le if e['type']=='supplier_accrual'])-total([e for e in le if e['type']=='supplier_credit'])-total([e for e in le if e['type']=='supplier_payout']))
        own_costs=[x for x in costs if key(x)==lk];own_events=[e for e in pe if e['type'] in ['fulfilled','refund']]
        order_revenue=revenue(own_events)
        direct_cost=total(own_costs)+total([e for e in pe if e['type']=='settlement'],'fee_amount') if all(x['amount'] is not None for x in own_costs) else None
        if line['order_date']<=end:rows.append({**line,'product_name':products.get((lk[0],line['product_code']),{}).get('name',line['product_code']),
             'paid_gross':total([e for e in pe if e['type']=='payment']) if pe else None,'refund_amount':total([e for e in pe if e['type']=='refund']) if pe else None,
             'recognized_income':order_revenue,'direct_cost':direct_cost,'direct_contribution':round(order_revenue-direct_cost,2) if order_revenue is not None and direct_cost is not None and line.get('cost_complete') is True else None,
             'pending_channel':round(channel,2),'commission_balance':round(earned-commission_received,2) if earned is not None and line['collector']=='supplier' else None,
             'income_pending':bool(any(e['type']=='fulfilled' for e in le) and earned is None),
             'supplier_balance':None if supplier_unknown else round(balance,2),
             'fulfilled_quantity':total([e for e in le if e['type']=='fulfilled'],'quantity'),
             'shipped_quantity':total([e for e in le if e['type']=='shipped'],'quantity'),
             'settlement_overdue':bool(line['settle_due'] and line['settle_due']<end and (channel>.01 or (earned is not None and line['collector']=='supplier' and earned-commission_received>.01))),
             'paid_to_date':round(all_paid-all_ref,2)})
    relevant_props={x['_property'] for x in g['commerce_line']+g['commerce_cost']+g['commerce_product']}
    days=[(date.fromisoformat(start)+timedelta(days=i)).isoformat() for i in range((date.fromisoformat(end)-date.fromisoformat(start)).days+1)]
    covered={(r['property_id'],r['data']['day']) for r in records if r['kind']=='coverage' and r['data']['complete']}
    expected={(p,d) for p in relevant_props for d in days}
    complete=bool(expected) and expected<=covered and all(c['amount'] is not None for c in costs) and all(lines[key(e)].get('cost_complete') is True for e in income_events)
    known_cost=total(costs)+fees if all(c['amount'] is not None for c in costs) else None
    contribution=round(income_value-known_cost,2) if complete and income_value is not None and known_cost is not None else None
    paid_orders={(x['_property'],x['order_no']) for x in paid};fulfilled_orders={(x['_property'],x['order_no']) for x in f}
    # Exact-period payment cohorts: a refunded order is counted once, never divide unrelated cash periods.
    refunded_order_keys={(e['_property'],e['order_no']) for e in past if e['type']=='refund' and (e['_property'],e['order_no']) in paid_orders and e['amount']>0}
    shipping=[l for l in g['commerce_line'] if l['delivery']=='shipping' and l['order_date']<=end and l['status']!='cancelled' and any(key(e)==key(l) and e['type']=='payment' for e in past)]
    matured=[l for l in shipping if l['ship_due'] and l['ship_due']<=end and l['ship_due']<asof]
    on_time=sum(sum(e.get('quantity') or 0 for e in past if key(e)==key(l) and e['type']=='shipped' and e['day']<=l['ship_due'])>=l['quantity']-(l.get('cancelled_quantity') or 0) for l in matured)
    traffic=[x for x in g['commerce_traffic'] if inside(x) and x['level']=='platform']
    traffic_ready=bool(traffic) and all(x['cohort_complete'] and x['observed_through']<=asof and x['visitors'] is not None and x['paying_visitors'] is not None for x in traffic)
    # Latest known snapshot for each owned SKU/warehouse; absence never becomes stock=0.
    latest={}
    for x in sorted([x for x in g['commerce_stock'] if x['day']<=end],key=lambda x:(x['day'],x['_id'])):latest[(x['_property'],x['product_code'],x['warehouse'])]=x
    stock=[]
    for pk,p in products.items():
        if not p['owned_stock'] or not p['active']:continue
        ss=[x for (prop,code,warehouse),x in latest.items() if (prop,code)==pk]
        available=sum(x['on_hand']-x['reserved']-x['unusable'] for x in ss) if ss else None
        stock.append(dict(property_id=pk[0],code=pk[1],name=p['name'],unit=p['unit'],available=available,snapshot_day=min((x['day'] for x in ss),default=None),source_refs=[x['source_ref'] for x in ss]))
    m=dict(trade_amount=total(dated) if dated else None,paid_gmv=total(paid) if paid else None,paid_orders=len(paid_orders) if paid else None,
           average_order=ratio(total(paid),len(paid_orders)),paid_net=round(total(paid)-total(refunds),2) if paid or refunds else None,
           recognized_income=income_value,refunds=total(refunds) if paid or refunds else None,
           cohort_refund_rate=len(refunded_order_keys)/len(paid_orders) if paid_orders else None,
           fulfilled_orders=len(fulfilled_orders) if f else None,
           timely_shipping=on_time/len(matured) if matured else None,
           contribution=contribution,known_cost=known_cost if costs or fees or complete else None,cost_complete=complete,
           received=round(total([e for e in es if e['type']=='payment' and e['funds_location']=='bank'])+total([e for e in es if e['type'] in ['settlement','commission_received']])-total([e for e in es if e['type']=='refund' and e['funds_location']=='bank'])-total([e for e in es if e['type']=='commission_return']),2) if es else None,
           pending_channel=round(sum(r['pending_channel'] for r in rows),2) if rows else None,
           supplier_payable=round(sum(max(r['supplier_balance'],0) for r in rows if r['supplier_balance'] is not None),2) if rows and all(r['supplier_balance'] is not None for r in rows) else None,
           supplier_recovery=round(sum(max(-r['supplier_balance'],0) for r in rows if r['supplier_balance'] is not None),2) if rows else None,
           commission_pending=round(sum(max(r['commission_balance'] or 0,0) for r in rows),2) if rows and not any(r['collector']=='supplier' and r['income_pending'] for r in rows) else None,
           commission_returnable=round(sum(max(-(r['commission_balance'] or 0),0) for r in rows),2) if rows and not any(r['collector']=='supplier' and r['income_pending'] for r in rows) else None,
           daily_uv_sum=total(traffic,'visitors') if traffic and all(x['visitors'] is not None for x in traffic) else None,
           visitor_conversion=ratio(total(traffic,'paying_visitors'),total(traffic,'visitors')) if traffic_ready else None,
           out_of_stock=sum(x['available']==0 for x in stock if x['available'] is not None) if any(x['available'] is not None for x in stock) else None,
           unconfirmed_lines=sum(x['recognition']=='unconfirmed' for x in rows),missing_stock=sum(x['available'] is None for x in stock))
    modes=[]
    for mode,label in MODES.items():
        ls={k for k,l in lines.items() if l['mode']==mode};mp=[e for e in paid if key(e) in ls];mr=[e for e in refunds if key(e) in ls];mf=[e for e in f if key(e) in ls]
        rc=revenue(mf+mr);mc=[c for c in costs if c.get('order_no') and key(c) in ls];fee=total([e for e in es if e['type']=='settlement' and key(e) in ls],'fee_amount')
        ready=bool(mf+mr) and all(lines[key(e)].get('cost_complete') is True for e in mf+mr) and all(c['amount'] is not None for c in mc)
        modes.append(dict(mode=mode,label=label,paid_gmv=total(mp) if mp else None,paid_orders=len({(x['_property'],x['order_no']) for x in mp}) if mp else None,
                          refunds=total(mr) if mp or mr else None,recognized_income=rc,
                          direct_cost=total(mc)+fee if mc or fee or ready else None,direct_contribution=round(rc-total(mc)-fee,2) if ready and rc is not None else None))
    daily=[dict(day=d,paid_gmv=total([e for e in paid if e['day']==d]) if any(e['day']==d for e in paid) else None,
                income=revenue([e for e in income_events if e['day']==d])) for d in days]
    active_products=[p for p in products.values() if p['active']]
    product_stats=[]
    for pk,p in products.items():
        ls={k for k,l in lines.items() if (l['_property'],l['product_code'])==pk}
        pf=[e for e in f if key(e) in ls];pp=[e for e in paid if key(e) in ls];pr=[e for e in refunds if key(e) in ls]
        pc=[c for c in costs if c.get('order_no') and key(c) in ls];pv=revenue(pf+pr)
        pfee=total([e for e in es if e['type']=='settlement' and key(e) in ls],'fee_amount')
        pc_ready=bool(pf+pr) and all(lines[key(e)].get('cost_complete') is True for e in pf+pr) and all(c['amount'] is not None for c in pc)
        product_stats.append({**p,'paid_gmv':total(pp) if pp else None,'fulfilled_quantity':total(pf,'quantity') if pf else None,'recognized_income':pv,'direct_contribution':round(pv-total(pc)-pfee,2) if pc_ready and pv is not None else None})
    m['active_skus']=len(active_products) if products else None
    m['active_sku_rate']=len({(lines[key(e)]['_property'],lines[key(e)]['product_code']) for e in f if (lines[key(e)]['_property'],lines[key(e)]['product_code']) in products and products[(lines[key(e)]['_property'],lines[key(e)]['product_code'])]['active']})/len(active_products) if active_products else None
    advertising=[c for c in costs if c['category']=='advertising'];campaigns={(c['_property'],c['campaign_code']) for c in advertising if c['campaign_code']}
    attributed=[e for e in paid if lines[key(e)]['traffic']=='paid' and (e['_property'],lines[key(e)]['campaign_code']) in campaigns]
    m['advertising_spend']=total(advertising) if advertising and all(c['amount'] is not None for c in advertising) else None
    m['attributed_roas']=ratio(total(attributed),m['advertising_spend']) if campaigns and attributed and all(c['campaign_code'] for c in advertising) else None
    channels=[]
    for channel in sorted({l['channel'] for l in lines.values()}):
        keys={k for k,l in lines.items() if l['channel']==channel};cp=[e for e in paid if key(e) in keys];cf=[e for e in f if key(e) in keys];cr=[e for e in refunds if key(e) in keys]
        channels.append(dict(channel=channel,paid_gmv=total(cp) if cp else None,paid_orders=len({(e['_property'],e['order_no']) for e in cp}) if cp else None,refunds=total(cr) if cp or cr else None,recognized_income=revenue(cf+cr)))
    return dict(metrics=m,channels=channels,modes=modes,lines=rows,products=product_stats,events=es,costs=costs,traffic=traffic,stock=stock,daily=daily,
                missing_cost_days=len(expected-covered),unknown_shipping_due=sum(not l['ship_due'] for l in shipping),
                updated_at=max((r['updated_at'] for r in records if r['kind'] in KINDS or r['kind']=='coverage'),default=None),
                note='森活优选为独立经营口径；GMV不加进园区收入。净额合作仅确认已履约佣金/服务费，代收本金不是收入；正式合并需按实际主体及内部交易对账抵消。')


def redact(result,user):
    if user['role']!='operations':return result
    hidden={'recognized_income','known_cost','contribution','cost_complete','received','pending_channel','supplier_payable','supplier_recovery','commission_pending','commission_returnable','advertising_spend','attributed_roas'}
    result['metrics']={k:v for k,v in result['metrics'].items() if k not in hidden}
    result['costs']=[]
    result['lines']=[{k:v for k,v in x.items() if k not in {'recognized_income','direct_cost','direct_contribution','pending_channel','commission_balance','supplier_balance','cost_complete'}} for x in result['lines']]
    result['modes']=[{k:v for k,v in x.items() if k not in {'recognized_income','direct_cost','direct_contribution'}} for x in result['modes']]
    result['products']=[{k:v for k,v in x.items() if k not in {'recognized_income','direct_contribution'}} for x in result['products']]
    result['channels']=[{k:v for k,v in x.items() if k!='recognized_income'} for x in result['channels']]
    result['events']=[{k:v for k,v in x.items() if k not in PRIVATE_EVENT} for x in result['events'] if x['type'] in ['shipped','fulfilled']]
    result['daily']=[{'day':x['day'],'paid_gmv':x['paid_gmv']} for x in result['daily']]
    return result
