"""Business-specific operating quantities and deterministic, traceable sector KPIs."""
from datetime import date, timedelta

NAMES = {'room': '住宿', 'dining': '餐饮', 'water': '游乐 / 水世界', 'spa': '温泉 / SPA', 'goods': '零售与会员'}
PRIMARY = {'hotel': 'room', 'restaurant': 'dining', 'water': 'water', 'spa': 'spa'}
COMMON = ['day', 'business', 'is_open', 'complete']
FIELDS = {
    'dining': ['available_tables', 'meal_periods', 'served_tables', 'waste_cost', 'labor_hours'],
    'water': ['visitors', 'daily_capacity', 'safety_incidents', 'labor_hours'],
    'spa': ['visitors', 'appointments', 'completed_appointments', 'available_minutes', 'used_minutes', 'labor_hours'],
    'goods': ['labor_hours'],
}


def schema(f):
    fields = {
        'day': f('营业日期', 'date'),
        'business': f('业务板块', 'select', True, list(FIELDS)),
        'is_open': f('当天实际营业', 'bool'),
        'complete': f('运营数量已核对（不代表成本完整）', 'bool'),
        'available_tables': f('实际开放餐桌数', 'integer', False),
        'meal_periods': f('实际营业餐次（如午晚餐为2）', 'integer', False),
        'served_tables': f('实际开台桌次（不是订单数）', 'integer', False),
        'waste_cost': f('食材损耗金额（已含耗用，不重复记费用）', 'number', False),
        'visitors': f('实际入园 / 服务人次（含免费）', 'integer', False),
        'daily_capacity': f('核准当日接待上限（人次，非瞬时容量）', 'integer', False),
        'safety_incidents': f('已核对安全事件数（无事件填0）', 'integer', False),
        'appointments': f('归属当天的预约总数（同批预约）', 'integer', False),
        'completed_appointments': f('上述预约中实际完成数', 'integer', False),
        'available_minutes': f('全部开放工位可服务分钟数', 'integer', False),
        'used_minutes': f('上述工位实际占用分钟数', 'integer', False),
        'labor_hours': f('实际出勤总工时', 'number', False),
        'source_ref': f('原系统 / 日结凭证编号', 'text', False),
        'owner': f('核对负责人'),
        'note': f('营业、数量及口径说明', 'text', False),
    }
    return dict(label='分业态营业与运营日报', fields=fields)


def template_fields(business):
    if business not in FIELDS:
        raise ValueError('请选择餐饮、游乐、温泉SPA或零售板块')
    return COMMON + FIELDS[business] + ['source_ref', 'owner', 'note']


def validate(d):
    applicable = set(template_fields(d['business']))
    for name in set().union(*FIELDS.values()) - applicable:
        if d.get(name) is not None:
            raise ValueError('此数量字段不适用于当前业务板块：' + name)
    if not d['is_open']:
        if any(d.get(k) not in (None, 0) for k in FIELDS[d['business']]):
            raise ValueError('停业日的实际运营数量应为0或未知，不可记录为已营业')
    if d.get('completed_appointments') is not None and d.get('appointments') is not None:
        if d['completed_appointments'] > d['appointments']:
            raise ValueError('同批预约完成数不能大于预约总数，散客请计入服务人次')
    if d['is_open'] and d.get('meal_periods') == 0:
        raise ValueError('营业餐次必须大于0或留空待确认')


def closed_project_days(g):
    """A restaurant/seasonal calendar closes its project, never an attached hotel."""
    answer = set()
    for p in g['property']:
        key = PRIMARY.get(p['business'])
        if not key or key == 'room':continue
        rows = [x for x in g.get('business_day', []) if x['_property']==p['code']]
        for d in {x['day'] for x in rows}:
            current = [x for x in rows if x['day']==d]
            if any(x['business']==key for x in current) and not any(x['is_open'] for x in current):
                answer.add((p['code'],d))
    return answer


# key, label, unit, formula, source type, financial permission
CARDS = {
    'room': [
        ('revenue', '客房净履约收入', '元', '客房权益履约收入 − 分摊到客房的退款冲回', 'fulfillment', False),
        ('nights', '实际售出间夜', '间夜', '已发生住宿履约间夜合计', 'fulfillment', False),
        ('occupancy', '客房入住率', '%', '实际售出间夜 ÷ 完整逐日可售间夜', 'inventory', False),
        ('adr', '平均房价 ADR', '元', '客房净履约收入 ÷ 实际售出间夜', 'fulfillment', False),
        ('revpar', 'RevPAR', '元', '客房净履约收入 ÷ 完整逐日可售间夜', 'inventory', False),
        ('booking7', '未来7天预订进度', '%', '未来确认预约间夜 ÷ 完整未来可售间夜', 'reservation', False),
        ('booking30', '未来30天预订进度', '%', '未来确认预约间夜 ÷ 完整未来可售间夜', 'reservation', False),
        ('out_of_service', '维修停用间夜', '间夜', '所选期间、住宿项目的逐日维修停用合计', 'inventory', False),
    ],
    'dining': [
        ('revenue', '餐饮净履约收入', '元', '餐饮权益收入 − 餐饮退款冲回；赠送早餐不加收入', 'fulfillment', False),
        ('paid_guests', '收费用餐人次', '人次', '收费餐饮履约的实际用餐人次，不含赠送早餐', 'fulfillment', False),
        ('average_spend', '收费餐饮客单', '元/人次', '餐饮净履约收入 ÷ 收费用餐人次；退款不扣实际到店人次', 'fulfillment', False),
        ('table_turns', '每餐桌台周转', '次/餐', '实际开台桌次 ÷ Σ(当日开放桌数 × 营业餐次)，按容量加权', 'business_day', False),
        ('food_cost_ratio', '食材耗用率', '%', '已归属餐饮的食材耗用成本 ÷ 餐饮净履约收入；采购不等于耗用', 'cost', True),
        ('waste_ratio', '食材损耗占比', '%', '已核对食材损耗金额 ÷ 食材耗用成本；损耗不重复计费用', 'business_day', True),
        ('banquet_orders', '宴会 / 团建履约单', '单', '宴会或团建的不同已履约订单数；按订单去重', 'fulfillment', False),
        ('redlines', '未关闭餐饮红线', '项', '餐厅及厨房未关闭红线，不被其他评分抵消', 'issue', False),
    ],
    'water': [
        ('revenue', '游乐净履约收入', '元', '游乐实际履约收入 − 对应退款冲回；售券未核销不认收入', 'fulfillment', False),
        ('visitors', '实际入园人次', '人次', '闸机或人工核对的入园人次，含免票；不以售票数代替', 'business_day', False),
        ('average_spend', '入园人均收入', '元/人次', '游乐净履约收入 ÷ 同期实际入园人次', 'business_day', False),
        ('operating_days', '实际营业项目日', '项目日', '逐项目逐日实际开园日数；多项目同日分别计数', 'business_day', False),
        ('daily_revenue', '营业日日均收入', '元/项目日', '营业日发生的净履约收入 ÷ 实际营业项目日；停业日退款另列', 'business_day', False),
        ('capacity_usage', '日接待承载利用率', '%', '实际入园人次 ÷ Σ营业日核准日接待上限；不是瞬时在园率', 'business_day', False),
        ('reversal', '游乐收入退款冲回', '元', '明确分摊到游乐权益的收入冲回，非全部现金退款', 'payment', False),
        ('safety_incidents', '已登记安全事件', '起', '已核对营业日报的安全事件合计；漏报日期保留未知', 'business_day', False),
    ],
    'spa': [
        ('revenue', '温泉 / SPA净收入', '元', '温泉SPA权益履约收入 − 对应退款冲回', 'fulfillment', False),
        ('visitors', '实际服务人次', '人次', '核对后的实际服务人次，预约与散客均包括，不是售卡份数', 'business_day', False),
        ('average_spend', '服务人均收入', '元/人次', '温泉SPA净履约收入 ÷ 实际服务人次', 'business_day', False),
        ('appointment_completion', '同批预约完成率', '%', '归属所选服务日的预约实际完成数 ÷ 同批预约总数', 'business_day', False),
        ('time_usage', '服务工位时段利用率', '%', '全部工位实际占用分钟 ÷ 全部开放工位可服务分钟', 'business_day', False),
        ('labor_productivity', '每工时履约收入', '元/工时', '温泉SPA净履约收入 ÷ 实际出勤总工时', 'business_day', False),
        ('operating_days', '实际营业项目日', '项目日', '完整营业日历中的实际开放项目日', 'business_day', False),
        ('redlines', '未关闭温泉SPA红线', '项', '温泉SPA部门未关闭服务及安全红线', 'issue', False),
    ],
    'goods': [
        ('revenue', '零售净履约收入', '元', '已交付商品收入 + 代销净服务收入 − 对应退款冲回', 'fulfillment', False),
        ('fulfilled_orders', '已交付零售订单', '单', '商品或代销净服务已履约订单去重，不以支付单代替', 'fulfillment', False),
        ('average_order', '零售履约单均收入', '元/单', '零售净履约收入 ÷ 已交付零售订单数', 'fulfillment', False),
        ('reversal', '零售收入退款冲回', '元', '归属商品或代销净服务的收入冲回；不含货主本金', 'payment', False),
        ('allocated_cost', '明确归属零售成本', '元', '显式分配到商品及代销净服务业务的已录入成本', 'cost', True),
        ('known_balance', '零售已知差额', '元', '零售净收入 − 明确归属成本；未分摊公共费用，不是净利润', 'cost', True),
        ('membership_revenue', '会员权益已履约收入', '元', '仅membership权益实际履约收入；售卡收款不直接确认为收入', 'fulfillment', False),
        ('unrecognized_rights', '未履约权益分摊额', '元', '当前授权项目已登记权益的未履约合同分摊额；不等同现金预收', 'entitlement', False),
    ],
}


def augment(result, g, start, end, asof, source_records):
    inside = lambda x: start <= x.get('day', '') <= end
    total = lambda rows, key='amount': round(sum(x.get(key) or 0 for x in rows), 2)
    days = [(date.fromisoformat(start) + timedelta(days=i)).isoformat()
            for i in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)]
    properties = {p['code']: p for p in g['property']}
    orders = {(o['_property'], o['order_no']): o for o in g['order']}
    fs = [x for x in g['fulfillment'] if inside(x)]
    cuts = [x for x in result['refund_allocations'] if inside(x)]
    all_days = [x for x in g.get('business_day', []) if inside(x)]
    costs = [x for x in g['cost'] if inside(x) and x['scope'] == 'park']
    sectors = {}
    for key, name in NAMES.items():
        businesses = {'goods', 'consignment_fee'} if key == 'goods' else {key}
        selected = [x for x in fs if x['business'] in businesses]
        refunds = [x for x in cuts if x['business'] in businesses]
        ledger_days = [x for x in all_days if x['business'] == key]
        expected_props = {p['code'] for p in properties.values()
                          if PRIMARY.get(p['business']) == key and p['status'] not in ['closed', 'planning']}
        expected_props |= {x['_property'] for x in selected + ledger_days}
        expected_props |= {x['property_id'] for x in refunds}
        expected = {(p, d) for p in expected_props for d in days}
        daily_map = {(x['_property'], x['day']): x for x in ledger_days}
        missing = expected - set(daily_map)
        calendar_complete = bool(expected) and not missing
        opened = [x for x in ledger_days if x['is_open']]
        open_keys = {(x['_property'], x['day']) for x in opened}
        def quantity(field):
            if not calendar_complete or any(not x['complete'] or x.get(field) is None for x in opened):
                return None
            return total(opened, field)
        def ratio(numerator, denominator):
            return numerator / denominator if numerator is not None and denominator is not None and denominator > 0 else None
        revenue = round(total(selected) - total(refunds), 2) if selected or refunds else None
        allocated = [x for x in costs if x.get('business') in businesses]
        known_cost = total(allocated) if allocated and all(x['amount'] is not None for x in allocated) else None
        food = [x for x in allocated if x['category'] == 'food']
        food_cost = total(food) if food and all(x['amount'] is not None for x in food) else None
        food_keys = {(x['_property'],x['day']) for x in food if x['amount'] is not None}
        finance_confirmed = {(x['_property'],x['day']) for x in g['coverage'] if x['complete']}
        food_complete = bool(food) and calendar_complete and bool(open_keys) and open_keys <= food_keys and open_keys <= finance_confirmed and food_cost is not None
        paid = [x for x in selected if not x['included'] and x['amount'] > 0]
        guests = total(paid, 'guests') if paid and all(x.get('guests') is not None for x in paid) else None
        visitors = quantity('visitors') if key in ['water', 'spa'] else None
        redline_departments = {'dining', 'kitchen'} if key == 'dining' else {'rooms','frontdesk','cleaning'} if key=='room' else {key}
        redlines = [x for x in g['issue'] if x['department'] in redline_departments and x['severity'] == 'redline' and x['status'] != 'closed']
        fulfilled_keys = {(x['_property'], x['order_no']) for x in selected}
        evidence_keys = fulfilled_keys | {(x['property_id'],x['order_no']) for x in refunds}
        v = dict(revenue=revenue, reversal=total(refunds) if selected or refunds else None,
                 fulfilled_orders=len(fulfilled_keys) if selected else None,
                 paid_guests=guests, visitors=visitors, food_cost=food_cost,
                 included_guests=(total([x for x in selected if x['included']], 'guests')
                                  if selected and all(x.get('guests') is not None for x in selected if x['included']) else None),
                 allocated_cost=known_cost,
                 known_balance=round(revenue-known_cost, 2) if revenue is not None and known_cost is not None else None,
                 operating_days=len(opened) if calendar_complete else None,
                 redlines=len(redlines),
                 average_spend=ratio(revenue, guests if key == 'dining' else visitors),
                 food_cost_complete=food_complete,
                 food_cost_ratio=ratio(food_cost, revenue) if food_complete else None,
                 waste_ratio=ratio(quantity('waste_cost'), food_cost) if key == 'dining' and food_complete else None,
                 table_turns=None,
                 banquet_orders=len({(x['_property'], x['order_no']) for x in selected if x.get('guest_type') in ['banquet', 'team']}) if selected else None,
                 capacity_usage=ratio(visitors, quantity('daily_capacity')) if key == 'water' else None,
                 safety_incidents=quantity('safety_incidents') if key == 'water' else None,
                 appointment_completion=ratio(quantity('completed_appointments'), quantity('appointments')) if key == 'spa' else None,
                 time_usage=ratio(quantity('used_minutes'), quantity('available_minutes')) if key == 'spa' else None,
                 labor_productivity=ratio(revenue, quantity('labor_hours')),
                 average_order=ratio(revenue, len(fulfilled_keys)),
                 membership_revenue=next((b['net_revenue'] for b in result['breakdown'] if b['business']=='membership'), None),
                 unrecognized_rights=total(result['entitlements'], 'unrecognized_allocation') if result['entitlements'] else None)
        if key == 'dining' and calendar_complete and all(x['complete'] and x.get('available_tables') is not None and x.get('meal_periods') is not None for x in opened):
            v['table_turns'] = ratio(quantity('served_tables'), sum(x['available_tables'] * x['meal_periods'] for x in opened))
        daily = []
        for d in days:
            f = [x for x in selected if x['day'] == d]; r = [x for x in refunds if x['day'] == d]
            daily.append({'day': d, 'revenue': round(total(f)-total(r), 2) if f or r else None})
        open_fulfillments = [x for x in selected if (x['_property'],x['day']) in open_keys]
        open_refunds = [x for x in refunds if (x['property_id'],x['day']) in open_keys]
        open_revenue = round(total(open_fulfillments)-total(open_refunds), 2) if open_fulfillments or open_refunds else None
        v['daily_revenue'] = ratio(open_revenue, v['operating_days'])
        if key == 'room':
            m = result['metrics']
            v.update(nights=m['room_nights'] if selected else None, available=m['available'],occupancy=m['occupancy'], adr=m['adr'], revpar=m['revpar'],
                     booking7=result['future_summary']['7']['pace'], booking30=result['future_summary']['30']['pace'],
                     out_of_service=total([x for x in g['inventory'] if inside(x) and properties.get(x['_property'],{}).get('business')=='hotel'], 'out_of_service') if m['inventory_complete'] else None)
        cards = [dict(key=k, label=label, unit=unit, formula=formula, kind=kind, financial=fin, value=v.get(k))
                 for k,label,unit,formula,kind,fin in CARDS[key]]
        groups = []
        if key == 'dining':
            for guest_type in ['resident', 'walkin', 'banquet', 'team', 'not_applicable']:
                rows = [x for x in selected if x.get('guest_type') == guest_type]
                rs = [x for x in refunds if x.get('guest_type', 'not_applicable') == guest_type]
                paying = [x for x in rows if not x['included'] and x['amount'] > 0]
                n = total(paying, 'guests') if paying and all(x.get('guests') is not None for x in paying) else None
                rev = round(total(rows)-total(rs), 2) if rows or rs else None
                groups.append(dict(guest_type=guest_type, revenue=rev, paid_guests=n,
                                   included_guests=total([x for x in rows if x['included']], 'guests') if rows and all(x.get('guests') is not None for x in rows if x['included']) else None,
                                   average_spend=ratio(rev,n)))
        ids = {x['_id'] for x in selected} | {x['_id'] for x in allocated} | {x['_id'] for x in ledger_days} | {x.get('payment_id') for x in refunds}
        ids |= {x['_id'] for x in g['coverage'] if inside(x) and x['_property'] in expected_props}
        if key=='room':ids |= {x['_id'] for x in g['inventory']+g['reservation'] if x['_property'] in expected_props}
        timestamp = max((x['updated_at'] for x in source_records if x['id'] in ids), default=None)
        sector_orders = []
        for order_key in sorted(evidence_keys):
            o = orders.get(order_key)
            if not o:continue
            of = [x for x in selected if (x['_property'],x['order_no'])==order_key]
            op = [x for x in refunds if (x['property_id'],x['order_no'])==order_key]
            sector_orders.append(dict(id=o['_id'],property_id=order_key[0],order_no=order_key[1],channel=o['channel'],revenue=round(total(of)-total(op),2)))
        sectors[key] = dict(key=key, name=name, metrics=v, cards=cards, daily=daily,
                            fulfillments=selected, refunds=refunds, costs=allocated, operating_records=ledger_days,
                            orders=sector_orders,order_ids=[o['id'] for o in sector_orders],
                            guest_groups=groups, calendar_complete=calendar_complete,
                            missing_days=len(missing), missing_inputs=sorted([dict(property_id=p,day=d) for p,d in missing], key=lambda x:(x['property_id'],x['day'])),
                            recorded_open_days=len(opened), operating_fields=template_fields(key) if key in FIELDS else [],
                            updated_at=timestamp,
                            scope_note='仅统计本业务权益和明确归属成本；套餐按分摊权益计入，未分摊公共成本不计入此处差额。')
        if key=='room':
            sectors[key]['inventory_records']=[x for x in g['inventory'] if inside(x) and properties.get(x['_property'],{}).get('business')=='hotel']
    result['sectors'] = sectors
    result['sector_scope'] = dict(property_count=len(properties), primary_business=(PRIMARY.get(next(iter(properties.values()))['business']) if len(properties)==1 else None))
    result['unallocated_cost'] = total([x for x in costs if not x.get('business')]) if costs else None
    return result


def redact_operations(result):
    """Do not expose costs via the new sector summaries or underlying evidence."""
    result.pop('unallocated_cost', None)
    hidden = {'food_cost','food_cost_ratio','food_cost_complete','waste_ratio','allocated_cost','known_balance'}
    for sector in result['sectors'].values():
        sector['cards'] = [c for c in sector['cards'] if not c['financial']]
        sector['metrics'] = {k:v for k,v in sector['metrics'].items() if k not in hidden}
        sector['costs'] = []
        sector['operating_records'] = [{k:v for k,v in r.items() if k!='waste_cost'} for r in sector['operating_records']]
