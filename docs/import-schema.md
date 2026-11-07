# 导入字段字典

各类型文件使用 UTF-8 CSV 或 Excel .xlsx，列顺序与模板一致。每批固定归属一个项目与一个数据集。多工作表合集用于查阅；实际导入请下载单类型模板或将目标工作表另存为单表文件。

external_id 为必填稳定业务编号。同类型、同数据集、同项目、同编号且内容一致会跳过；内容改变须显式编辑。数字不含千分位，可选金额留空表示未知；日期 YYYY-MM-DD，布尔 true/false。

## 酒店与项目 / property

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|code|项目代码|text|是||
|name|名称|text|是||
|business|业务|select|是|hotel, restaurant, water, spa, other|
|status|开放状态|select|是|unconfirmed, open, seasonal, planning, closed|
|planned_rooms|规划房量|integer|否||
|physical_rooms|物理房量|integer|否||
|note|待确认背景|text|否||

## 逐日房态 / 营业日历 / inventory

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|day|日期|date|是||
|room_type|房型 / 项目|text|是||
|physical|当日物理房量|integer|是||
|out_of_service|维修停用|integer|是||
|available|当日可售房量|integer|是||
|locked|锁房（可售内保留）|integer|是||
|voucher_commitment|未预约券承诺|integer|是||
|is_open|实际营业|bool|是||
|day_type|日类型|select|是|workday, weekend, holiday|
|rate|参考房价|number|否||

## 订单 / order

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|order_no|订单号|text|是||
|order_date|下单日期|date|是||
|checkin|服务开始日|date|是||
|checkout|结束日（住宿离店日）|date|是||
|kind|订单类型|select|是|stay, dining, water, spa, voucher, membership, goods, consignment, other|
|status|订单状态|select|是|confirmed, completed, cancelled|
|booking_amount|交易额（退款前）|number|是||
|customer_code|客户匿名编号|text|否||
|channel|最终成交渠道|select|是|unknown, douyin, xiaohongshu, wechat, ctrip, meituan, dianping, miniapp, private, offline, other|
|discovery|首次发现来源|text|否||
|assist|辅助影响来源|text|否||
|traffic|流量属性|select|是|unknown, organic, paid|
|campaign_code|营销活动编号|text|否||
|contract_code|结算合同代码|text|否||
|owner|跟进负责人|text|否||
|principal_amount|代销应付货主本金（非代销留空）|number|否||

## 每日预约 / reservation

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|order_no|订单号|text|是||
|day|入住夜日期|date|是||
|room_type|房型|text|是||
|rooms|预订房间数|integer|是||
|status|预约状态|select|是|confirmed, cancelled|

## 履约与套餐分摊 / fulfillment

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|order_no|订单号|text|是||
|day|履约日期|date|是||
|business|收入业务|select|是|room, dining, water, spa, goods, consignment_fee, membership, other|
|amount|本权益已履约收入|number|是||
|room_nights|实际售出间夜|integer|是||
|included|房费内赠送权益（收入必须为0）|bool|是||
|guest_type|餐饮客群|select|是|not_applicable, resident, walkin, banquet, team|
|guests|用餐/服务人数|integer|否||
|room_type|客房房型（未知留空）|text|否||
|product_code|产品代码|text|否||
|entitlement_code|核销权益代码|text|否||
|redeemed_units|核销份数|number|否||

## 收款 / 退款 / 到账 / payment

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|order_no|订单号|text|是||
|day|发生日期|date|是||
|type|资金类型|select|是|collection, refund, settlement, principal_payout, platform_fee|
|destination|资金位置|select|是|platform, bank|
|amount|金额|number|是||
|revenue_reversal|退款中冲减已履约收入|number|是||
|due_date|预计结算日期|date|否||
|principal_reversal|退款中冲减货主本金（非代销留空）|number|否||
|fulfillment_ref|定向冲回的履约外部编号（空为按剩余权益分摊）|text|否||

## 经营成本 / cost

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|day|归属日期|date|是||
|category|成本科目|select|是|payroll, utilities, food, supplies, laundry, repair, marketing, rent, fixed, other|
|amount|金额（未知可留空）|number|否||
|scope|费用归属|select|是|park, operator|
|order_no|关联订单（可空）|text|否||
|note|说明|text|否||
|business|归属业务（空为未分摊）|select|否|room, dining, water, spa, goods, consignment_fee, membership, other|
|product_code|分摊产品代码|text|否||

## 成本完整性确认 / coverage

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|day|归属日期|date|是||
|complete|全部成本已录入|bool|是||
|owner|确认负责人|text|是||
|note|缺失项目 / 口径|text|否||

## 运营结算合同 / contract

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|code|合同代码|text|是||
|start|生效日|date|是||
|end|到期日|date|是||
|rate|佣金比例（0至1）|number|是||
|basis|计佣依据|select|是|fulfilled, paid_net|
|beneficiary|收款方|select|是|operator, external|
|settlement_days|结算账期天数|integer|是||
|note|实际合同说明|text|否||

## 运营公司独立账 / operator_entry

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|day|日期|date|是||
|type|项目|select|是|service_revenue, goods_revenue, membership_fulfilled, commission_received, commission_expense|
|amount|金额|number|是||
|contract_code|关联合同|text|否||
|note|说明（不计园区交易额）|text|否||

## 内容 / 直播 / 获客 / campaign

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|code|活动编号|text|是||
|day|日期|date|是||
|channel|渠道|text|是||
|format|内容形式|select|是|video, live, creator, ads, ota, miniapp, private|
|traffic|流量属性|select|是|organic, paid, unknown|
|impressions|曝光次数|integer|否||
|viewers|观看人数|integer|否||
|consultations|有效咨询人数|integer|否||
|spend|获客花费（计入贡献，不再重复录营销成本）|number|否||
|owner|负责人|text|否||

## 客户与咨询 / customer

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|code|匿名客户编号|text|是||
|phone_last4|手机号末4位（仅脱敏存储）|text|否||
|day|咨询日期|date|是||
|owner|跟进负责人|text|是||
|response_minutes|首次响应分钟|number|否||
|reason|未成交原因|text|否||
|status|跟进状态|select|是|new, following, converted, lost|

## SOP 与异常整改 / issue

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|day|发现日|date|是||
|department|部门|select|是|frontdesk, rooms, dining, cleaning, kitchen, finance, marketing, data, water, spa, goods|
|title|问题 / 检查项|text|是||
|severity|严重性|select|是|normal, major, redline|
|order_no|关联订单|text|否||
|evidence|发现证据 / 原始记录编号|text|是||
|owner|负责人|text|是||
|due_date|截止日期|date|是||
|status|整改状态|select|是|open, in_progress, review, closed|
|remediation|整改证据|text|否||
|review_result|复查结果|text|否||
|reviewer|复查人|text|否||
|alert_key|来源预警/检查标识|text|否||

## 目标 / 预算 / 预测 / target

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|start|开始日期|date|是||
|end|结束日期|date|是||
|channel|渠道（空为全渠道）|text|否||
|scenario|口径|select|是|budget, forecast|
|revenue|已履约收入目标|number|否||
|cost|经营成本预算|number|否||
|occupancy|入住率目标0至1|number|否||
|owner|负责人|text|是||

## 预警规则与责任分工 / alert_rule

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|code|规则|select|是|booking7, booking30, refund_ratio, budget, negative_contribution, settlement, data_quality, service_redline|
|channel|渠道（空为全渠道）|text|否||
|enabled|启用|bool|是||
|threshold|阈值（比例用0至1）|number|否||
|severity|严重性|select|是|normal, major, redline|
|owner|默认负责人|text|是||
|deadline_days|处理期限天数|integer|是||

## 产品与权益目录 / product

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|code|产品代码|text|是||
|name|名称|text|是||
|business|业务|select|是|room, dining, water, spa, goods, consignment_fee, membership, other|
|active|在售|bool|是||
|unit|计量单位|text|是||
|reference_price|参考单价（不代替实绩）|number|否||
|owner|负责人|text|否||

## 会员 / 预售券权益 / entitlement

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|code|权益代码|text|是||
|order_no|发行订单号|text|是||
|product_code|产品代码|text|否||
|business|履约业务|select|是|room, dining, water, spa, goods, membership, other|
|quantity|发行份数|number|是||
|cancelled_units|已取消未核销份数|number|是||
|allocated_amount|分摊合同收入（非收款）|number|是||
|expires_on|有效期至|date|是||
|note|说明|text|否||

## 匿名客户触点事件 / touchpoint

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|day|发生日期|date|是||
|customer_code|匿名客户编号|text|是||
|campaign_code|活动代码|text|是||
|stage|触点阶段|select|是|view, consult|
|evidence|来源事件编号或证据|text|是||

## SOP检查标准 / sop_item

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|code|标准代码|text|是||
|department|部门|select|是|frontdesk, rooms, dining, cleaning, kitchen, water, spa, goods|
|title|检查项|text|是||
|standard|合格标准|text|是||
|redline|重大红线|bool|是||
|active|启用|bool|是||

## SOP执行检查 / sop_check

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|day|检查日期|date|是||
|item_code|检查标准代码|text|是||
|result|检查结果|select|是|pass, fail, not_applicable|
|evidence|实际检查证据|text|是||
|owner|检查/整改负责人|text|是||
|due_date|整改期限|date|是||

## 口碑与客户评价 / review

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|day|评价日期|date|是||
|channel|平台 / 来源|text|是||
|order_no|关联订单|text|否||
|rating|评分（1至5）|number|是||
|category|评价方面|select|是|service, cleanliness, kitchen, value, other|
|content|脱敏评价内容|text|是||
|owner|处理负责人|text|是||
|response|回复内容|text|否||
|status|处理状态|select|是|open, responded, resolved|

## 分业态营业与运营日报 / business_day

|字段|说明|类型|必填|枚举|
|---|---|---|---|---|
|external_id|稳定外部编号|text|是||
|day|营业日期|date|是||
|business|业务板块|select|是|dining, water, spa, goods|
|is_open|当天实际营业|bool|是||
|complete|运营数量已核对（不代表成本完整）|bool|是||
|available_tables|实际开放餐桌数|integer|否||
|meal_periods|实际营业餐次（如午晚餐为2）|integer|否||
|served_tables|实际开台桌次（不是订单数）|integer|否||
|waste_cost|食材损耗金额（已含耗用，不重复记费用）|number|否||
|visitors|实际入园 / 服务人次（含免费）|integer|否||
|daily_capacity|核准当日接待上限（人次，非瞬时容量）|integer|否||
|safety_incidents|已核对安全事件数（无事件填0）|integer|否||
|appointments|归属当天的预约总数（同批预约）|integer|否||
|completed_appointments|上述预约中实际完成数|integer|否||
|available_minutes|全部开放工位可服务分钟数|integer|否||
|used_minutes|上述工位实际占用分钟数|integer|否||
|labor_hours|实际出勤总工时|number|否||
|source_ref|原系统 / 日结凭证编号|text|否||
|owner|核对负责人|text|是||
|note|营业、数量及口径说明|text|否||
