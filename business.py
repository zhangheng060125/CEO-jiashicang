"""Business extensions: explicit allocations, entitlements, service quality and decision rules.
Pure functions; no environment initialization, persistence or external integrations.
"""
from datetime import date, timedelta
from hashlib import sha256

RULES={'booking7':'未来7天预订不足','booking30':'未来30天预订不足','refund_ratio':'退款异常','budget':'费用超预算','negative_contribution':'成熟订单贡献为负','settlement':'结算逾期','data_quality':'数据缺失','service_redline':'服务红线'}

def schemas(f):
 return {
  'alert_rule':dict(label='预警规则与责任分工',fields={'code':f('规则','select',True,list(RULES)),'channel':f('渠道（空为全渠道）','text',False),'enabled':f('启用','bool'),'threshold':f('阈值（比例用0至1）','number',False),'severity':f('严重性','select',True,['normal','major','redline']),'owner':f('默认负责人'),'deadline_days':f('处理期限天数','integer')}),
  'product':dict(label='产品与权益目录',fields={'code':f('产品代码'),'name':f('名称'),'business':f('业务','select',True,['room','dining','water','spa','goods','consignment_fee','membership','other']),'active':f('在售','bool'),'unit':f('计量单位'),'reference_price':f('参考单价（不代替实绩）','number',False),'owner':f('负责人','text',False)}),
  'entitlement':dict(label='会员 / 预售券权益',fields={'code':f('权益代码'),'order_no':f('发行订单号'),'product_code':f('产品代码','text',False),'business':f('履约业务','select',True,['room','dining','water','spa','goods','membership','other']),'quantity':f('发行份数','number'),'cancelled_units':f('已取消未核销份数','number'),'allocated_amount':f('分摊合同收入（非收款）','number'),'expires_on':f('有效期至','date'),'note':f('说明','text',False)}),
  'touchpoint':dict(label='匿名客户触点事件',fields={'day':f('发生日期','date'),'customer_code':f('匿名客户编号'),'campaign_code':f('活动代码'),'stage':f('触点阶段','select',True,['view','consult']),'evidence':f('来源事件编号或证据')}),
  'sop_item':dict(label='SOP检查标准',fields={'code':f('标准代码'),'department':f('部门','select',True,['frontdesk','rooms','dining','cleaning','kitchen']),'title':f('检查项'),'standard':f('合格标准'),'redline':f('重大红线','bool'),'active':f('启用','bool')}),
  'sop_check':dict(label='SOP执行检查',fields={'day':f('检查日期','date'),'item_code':f('检查标准代码'),'result':f('检查结果','select',True,['pass','fail','not_applicable']),'evidence':f('实际检查证据'),'owner':f('检查/整改负责人'),'due_date':f('整改期限','date')}),
  'review':dict(label='口碑与客户评价',fields={'day':f('评价日期','date'),'channel':f('平台 / 来源'),'order_no':f('关联订单','text',False),'rating':f('评分（1至5）','number'),'category':f('评价方面','select',True,['service','cleanliness','kitchen','value','other']),'content':f('脱敏评价内容'),'owner':f('处理负责人'),'response':f('回复内容','text',False),'status':f('处理状态','select',True,['open','responded','resolved'])})
 }

def validate(kind,d):
 if kind=='alert_rule':
  if d['code'] in ['booking7','booking30','refund_ratio'] and (d['threshold'] is None or not 0<=d['threshold']<=1):raise ValueError('比例阈值必须在0至1之间')
  if d['code']=='service_redline' and (not d['enabled'] or d['severity']!='redline'):raise ValueError('服务红线不能禁用或降低级别')
  if d['deadline_days']>365:raise ValueError('处理期限不能超过365天')
 if kind=='review':
  if not 1<=d['rating']<=5:raise ValueError('评价评分必须为1至5')
  if d['status']!='open' and not d['response']:raise ValueError('回复或解决评价必须记录实际回复')
 if kind=='entitlement':
  if not d['quantity'] or d['cancelled_units']>d['quantity']:raise ValueError('权益发行份数须大于0，取消数不得超过发行数')
 if kind=='sop_check' and d['due_date']<d['day']:raise ValueError('整改期限不能早于检查日期')
 if kind=='payment' and d.get('fulfillment_ref') and (d['type']!='refund' or d['revenue_reversal']<=0):raise ValueError('指定履约权益只适用于有收入冲回的退款')
 if kind=='fulfillment' and bool(d.get('entitlement_code'))!=bool(d.get('redeemed_units')):raise ValueError('权益代码与核销份数必须同时提供；普通履约均留空')

def reversal_allocations(fs,ps):
 """Allocate reversals in integer cents against remaining recognized lines.
 Targeted refunds apply to one explicit line; untargeted refunds consume remaining
 eligible revenue proportionately, never re-refunding a fully reversed right.
 """
 remaining={x['_external']:round(x['amount']*100) for x in fs}
 allocations=[]
 for p in sorted(ps,key=lambda x:(x['day'],x.get('_id',0))):
  cents=round(p.get('revenue_reversal',0)*100)
  if not cents:continue
  candidates=[x for x in fs if x['day']<=p['day'] and (not p.get('fulfillment_ref') or x['_external']==p['fulfillment_ref'])]
  if p.get('fulfillment_ref') and not candidates:raise ValueError('指定退款履约记录不存在、跨订单或晚于退款日')
  denominator=sum(remaining[x['_external']] for x in candidates)
  if cents>denominator:raise ValueError('收入冲回超过指定权益或订单的剩余已履约金额')
  if not denominator:continue
  shares=[(x,cents*remaining[x['_external']]//denominator,cents*remaining[x['_external']]%denominator) for x in candidates]
  leftover=cents-sum(amount for x,amount,remainder in shares)
  extras={x['_external'] for x,amount,remainder in sorted(shares,key=lambda s:(-s[2],s[0]['_external']))[:leftover]}
  for x,amount,remainder in shares:
   amount+=int(x['_external'] in extras)
   if not amount:continue
   remaining[x['_external']]-=amount
   allocations.append({'payment_id':p.get('_id'),'payment_ref':p.get('_external'),'fulfillment_ref':x['_external'],'day':p['day'],'amount':amount/100,'business':x['business'],'room_type':x.get('room_type') or 'unknown','product_code':x.get('product_code') or '', 'property_id':x.get('_property'),'order_no':x['order_no']})
 return allocations

def validate_relations(index):
 for (prop,kind),items in index.items():
  if kind=='property':continue
  group={k:v for (p,k),v in index.items() if p==prop}
  product={x['code']:x for x in group.get('product',[])};entitlements={x['code']:x for x in group.get('entitlement',[])}
  natural={'alert_rule':lambda x:(x['code'],x['channel']),'product':lambda x:x['code'],'entitlement':lambda x:x['code'],'sop_item':lambda x:x['code'],'target':lambda x:(x['start'],x['end'],x['channel'],x['scenario'])}
  if kind in natural:
   keys=[natural[kind](x) for x in items]
   if len(keys)!=len(set(keys)):raise ValueError('配置或业务代码重复，请编辑已有记录')
  for x in items:
   if x.get('product_code') and x['product_code'] not in product:raise ValueError('产品代码不存在')
   if kind in ['fulfillment','entitlement'] and x.get('product_code') and product[x['product_code']]['business']!=x['business']:raise ValueError('产品业务类型与履约或权益业务不一致')
   if kind=='touchpoint' and x['campaign_code'] not in {a['code'] for a in group.get('campaign',[])}:raise ValueError('触点关联活动不存在')
   if kind=='sop_check' and x['item_code'] not in {a['code'] for a in group.get('sop_item',[])}:raise ValueError('SOP检查标准不存在')
   if kind=='fulfillment' and x.get('entitlement_code'):
    e=entitlements.get(x['entitlement_code'])
    if not e or e['order_no']!=x['order_no'] or e['business']!=x['business']:raise ValueError('核销权益必须属于同订单及同业务')
    if x['day']>e['expires_on']:raise ValueError('核销日期超过权益有效期')
  if kind=='entitlement':
   for e in items:
    fs=[x for x in group.get('fulfillment',[]) if x.get('entitlement_code')==e['code']]
    if sum(x.get('redeemed_units') or 0 for x in fs)>e['quantity']-e['cancelled_units']+1e-8:raise ValueError('权益重复核销或取消，超过可用份数')
    if sum(x['amount'] for x in fs)>e['allocated_amount']+.001:raise ValueError('核销收入超过此权益分摊金额')
   orders={o['order_no']:o for o in group.get('order',[])}
   for no in {e['order_no'] for e in items}:
    if sum(e['allocated_amount'] for e in items if e['order_no']==no)>orders[no]['booking_amount']+.001:raise ValueError('权益分摊金额合计超过发行订单价')
  if kind=='order':
   for o in items:
    fs=[x for x in group.get('fulfillment',[]) if x['order_no']==o['order_no']];ps=[x for x in group.get('payment',[]) if x['order_no']==o['order_no']]
    reversal_allocations(fs,ps)


def augment(result,g,start,end,asof,allocations):
 """Add management views without mixing actual/budget/demo or writing on reads."""
 inside=lambda x:start<=x.get('day','')<=end
 total=lambda rows,key='amount':round(sum(x.get(key) or 0 for x in rows),2)
 orders={(o['_property'],o['order_no']):o for o in g['order']}
 fs=[x for x in g['fulfillment'] if inside(x)];ps=[x for x in g['payment'] if inside(x)]
 costs=[x for x in g['cost'] if inside(x) and x['scope']=='park'];campaigns=[x for x in g['campaign'] if inside(x)]
 refund_alloc=[a for a in allocations if start<=a['day']<=end]
 result['refund_allocations']=refund_alloc
 for b in result['breakdown']:
  cuts=total([a for a in refund_alloc if a['business']==b['business']])
  b['refund_reversal']=cuts
  b['net_revenue']=None if b['fulfilled_gross'] is None and not cuts else round((b['fulfilled_gross'] or 0)-cuts,2)
  b['known_contribution']=round(b['net_revenue']-b['allocated_cost'],2) if b['net_revenue'] is not None and b['allocated_cost'] is not None else None
 result['entitlements']=[]
 for e in g.get('entitlement',[]):
  of=[x for x in g['fulfillment'] if x['_property']==e['_property'] and x.get('entitlement_code')==e['code'] and x['day']<=end]
  used=total(of,'redeemed_units');remaining=e['quantity']-e['cancelled_units']-used
  result['entitlements'].append({**e,'redeemed_units':used,'remaining_units':remaining,'recognized_gross':total(of),'unrecognized_allocation':round(e['allocated_amount']-total(of),2),'expired':e['expires_on']<asof})
 result['products']=[]
 for p in g.get('product',[]):
  pf=[x for x in fs if x['_property']==p['_property'] and x.get('product_code')==p['code']]
  pc=[x for x in costs if x['_property']==p['_property'] and x.get('product_code')==p['code']]
  pr=[x for x in refund_alloc if x['property_id']==p['_property'] and x['product_code']==p['code']]
  rev=round(total(pf)-total(pr),2) if pf or pr else None
  cost=total(pc) if pc and all(x['amount'] is not None for x in pc) else None
  result['products'].append({**p,'revenue':rev,'allocated_cost':cost,'known_contribution':round(rev-cost,2) if rev is not None and cost is not None else None})
 # Budget comparisons are per exact period and scope, never sum channel and store budgets.
 result['target_comparisons']=[]
 for t in result['targets']:
  prop=t['_property'];ch=t.get('channel');keys={k for k,o in orders.items() if k[0]==prop and (not ch or o['channel']==ch)}
  tf=[x for x in fs if (x['_property'],x['order_no']) in keys];tp=[x for x in ps if (x['_property'],x['order_no']) in keys]
  tc=[x for x in costs if x['_property']==prop and (not ch or (prop,x.get('order_no')) in keys)]
  ca=[x for x in campaigns if x['_property']==prop and (not ch or x['channel']==ch)]
  commissions=[x for x in result['commissions'] if (x['property_id'],x['order_no']) in keys]
  revenue=round(total(tf)-total(tp,'revenue_reversal'),2) if tf or any(x['revenue_reversal'] for x in tp) else None
  cost=round(total(tc)+total(ca,'spend')+total(commissions),2)
  result['target_comparisons'].append({**t,'actual_revenue':revenue,'revenue_gap':round(revenue-t['revenue'],2) if revenue is not None and t['revenue'] is not None else None,'attainment':revenue/t['revenue'] if revenue is not None and t['revenue'] else None,'known_cost':cost,'cost_gap':round(cost-t['cost'],2) if t['cost'] is not None else None,'cost_scope':'渠道关联成本，不含未分摊公共成本' if ch else '项目已录入成本、活动花费和佣金'})
 # Cohort conversion only uses identifiable anonymous viewers. Aggregate exposure is excluded.
 result['cohorts']=[]
 for c in g['campaign']:
  touches=[x for x in g.get('touchpoint',[]) if x['_property']==c['_property'] and x['campaign_code']==c['code']]
  first={}
  for x in touches:
   if x['stage']=='view':first[x['customer_code']]=min(first.get(x['customer_code'],x['day']),x['day'])
  cohort={who:d for who,d in first.items() if start<=d<=end}
  if not cohort:continue
  stages={k:set() for k in ['consult','paid','reserved','refund','fulfilled','repeat']}
  for x in touches:
   if x['stage']=='consult' and x['customer_code'] in cohort and cohort[x['customer_code']]<=x['day']<=end:stages['consult'].add(x['customer_code'])
  for key,o in orders.items():
   who=o.get('customer_code')
   if key[0]!=c['_property'] or o.get('campaign_code')!=c['code'] or who not in cohort or not cohort[who]<=o['order_date']<=end:continue
   def linked(rows):return [x for x in rows if (x['_property'],x['order_no'])==key and cohort[who]<=x['day']<=end]
   for stage,rows in [('paid',[x for x in g['payment'] if x['type']=='collection']),('refund',[x for x in g['payment'] if x['type']=='refund']),('reserved',[x for x in g['reservation'] if x['status']=='confirmed']),('fulfilled',g['fulfillment'])]:
    if linked(rows):stages[stage].add(who)
   if who in stages['fulfilled']:
    historical={(x['_property'],x['order_no']) for x in g['fulfillment'] if x['day']<=end and orders.get((x['_property'],x['order_no']),{}).get('customer_code')==who}
    if len(historical)>1:stages['repeat'].add(who)
  result['cohorts'].append({'property_id':c['_property'],'campaign_code':c['code'],'traffic':c['traffic'],'viewers':len(cohort),**{k:len(v) for k,v in stages.items()},'paid_conversion':len(stages['paid'])/len(cohort),'asof':end})
 checks=[x for x in g.get('sop_check',[]) if inside(x)];items={(x['_property'],x['code']):x for x in g.get('sop_item',[])}
 inspected=[x for x in checks if x['result']!='not_applicable'];failed=[x for x in checks if x['result']=='fail']
 reviews=[x for x in g.get('review',[]) if inside(x)]
 redlines=[x for x in g['issue'] if x['severity']=='redline' and x['status']!='closed']
 result['service_quality']={'checked':len(inspected),'passed':sum(x['result']=='pass' for x in inspected),'pass_rate':sum(x['result']=='pass' for x in inspected)/len(inspected) if inspected else None,'failed':len(failed),'active_redlines':len(redlines),'rating':sum(x['rating'] for x in reviews)/len(reviews) if reviews else None,'review_count':len(reviews),'unanswered_reviews':sum(x['status']=='open' for x in reviews),'checks':checks,'reviews':reviews,'can_show_pass':bool(inspected) and not redlines and not failed}
 apply_rules(result,g,start,end,asof)
 return result


def apply_rules(result,g,start,end,asof):
 rules={(x['_property'],x['code'],x.get('channel','')):x for x in g.get('alert_rule',[])}
 def rule(prop,code,ch=''):
  return rules.get((prop,code,ch)) or rules.get((prop,code,'')) or {'enabled':True,'threshold':.2 if code=='refund_ratio' else .3,'owner':'','deadline_days':1,'severity':'major' if code not in ['booking7','booking30'] else 'normal'}
 alerts=[a for a in result['alerts'] if not(a['title'].startswith('逐日可售') or a['title'].startswith('成本口径')) and not(a['title'].startswith('未来') and '预订不足' in a['title']) and not a['title'].startswith('期间退款/') and not a['title'].startswith('已录入费用超过')]
 for prop in [p['code'] for p in g['property']]:
  iv=[x for x in g['inventory'] if x['_property']==prop]
  reservations=[x for x in g['reservation'] if x['_property']==prop and x['status']=='confirmed']
  property_info=next(p for p in g['property'] if p['code']==prop)
  if property_info['status'] not in ['planning','closed']:
   dates={(date.fromisoformat(start)+timedelta(days=i)).isoformat() for i in range((date.fromisoformat(end)-date.fromisoformat(start)).days+1)}
   types={x['room_type'] for x in iv} or {'unknown'};present={(x['day'],x['room_type']) for x in iv};missing={d for d in dates if any((d,t) not in present for t in types)}
   if property_info['business']=='hotel' and missing:alerts.append(dict(title='逐日可售房量缺失',rule_code='data_quality',property_id=prop,channel='',order_no='',department='data',evidence=f'缺少{len(missing)}天房态，入住率与RevPAR不能确认'))
   closed={x['day'] for x in iv if not any(y['is_open'] for y in iv if x['day']==y['day'])};covered={x['day'] for x in g['coverage'] if x['_property']==prop and x['complete']}
   missing=dates-closed-covered
   unknown=sum(x['amount'] is None for x in g['cost'] if x['_property']==prop and start<=x['day']<=end)
   if missing or unknown:alerts.append(dict(title='成本数据或完整性确认缺失',rule_code='data_quality',property_id=prop,channel='',order_no='',department='finance',evidence=f'缺少{len(missing)}天确认，{unknown}条成本金额未知，不能认定净利润'))
  for n in [7,30]:
   cfg=rule(prop,'booking'+str(n));days={(date.fromisoformat(asof)+timedelta(days=i)).isoformat() for i in range(n)}
   inv=[x for x in iv if x['day'] in days];den=sum(x['available'] for x in inv);booked=sum(x['rooms'] for x in reservations if x['day'] in days)
   if cfg['enabled'] and den and {x['day'] for x in inv}==days and booked/den<cfg['threshold']:
    alerts.append(dict(title=f'未来{n}天预订低于配置阈值',rule_code='booking'+str(n),property_id=prop,channel='',order_no='',department='marketing',evidence=f'确认{booked} / 可售{den}间夜；阈值{cfg["threshold"]:.1%}'))
  channels={''}|{r['channel'] for r in g.get('alert_rule',[]) if r['_property']==prop and r['code']=='refund_ratio' and r['channel']}
  for ch in channels:
   cfg=rule(prop,'refund_ratio',ch);keys={o['order_no'] for o in g['order'] if o['_property']==prop and (not ch or o['channel']==ch)}
   ps=[x for x in g['payment'] if x['_property']==prop and x['order_no'] in keys and start<=x['day']<=end]
   collected=sum(x['amount'] for x in ps if x['type']=='collection');refunded=sum(x['amount'] for x in ps if x['type']=='refund')
   if cfg['enabled'] and collected and refunded/collected>cfg['threshold']:alerts.append(dict(title='退款/收款超过配置阈值（非同批订单退款率）',rule_code='refund_ratio',property_id=prop,channel=ch,order_no='',department='finance',evidence=f'期间退款{refunded:.2f} / 收款{collected:.2f}；阈值{cfg["threshold"]:.1%}'))
 for t in result['target_comparisons']:
  if t['scenario']=='budget' and t['cost_gap'] is not None and t['cost_gap']>0:alerts.append(dict(title='费用超过匹配期间预算',rule_code='budget',property_id=t['_property'],channel=t['channel'],order_no='',department='finance',evidence=f'预算记录#{t["_id"]}：已知费用{t["known_cost"]:.2f} / 预算{t["cost"]:.2f}'))
 final=[]
 for a in alerts:
  code=a.get('rule_code') or ('settlement' if '逾期' in a['title'] else 'negative_contribution' if '贡献为负' in a['title'] else 'data_quality')
  prop=a.get('property_id','');cfg=rule(prop,code,a.get('channel',''))
  if not cfg['enabled']:continue
  a.update(rule_code=code,channel=a.get('channel',''),severity=cfg['severity'] if (prop,code,a.get('channel','')) in rules or (prop,code,'') in rules else a.get('severity',cfg['severity']),owner=cfg['owner'] or a.get('owner',''),due_date=(date.fromisoformat(asof)+timedelta(days=cfg['deadline_days'])).isoformat())
  subject=a.get('order_no') or a['title'];a['alert_key']=sha256(f'{code}|{prop}|{a["channel"]}|{subject}'.encode()).hexdigest()[:24]
  linked=[x for x in g['issue'] if x.get('alert_key')==a['alert_key']]
  active=next((x for x in reversed(linked) if x['status']!='closed'),None)
  a['task_id']=active['_id'] if active else None;a['task_status']=active['status'] if active else ('recurrence' if linked else 'unassigned')
  if active:a['owner']=active['owner'];a['due_date']=active['due_date']
  final.append(a)
 result['alerts']=final
