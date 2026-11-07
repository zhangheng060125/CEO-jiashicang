// Business-specific screens use server-calculated rights, refunds and operating quantities.
export function createSectors({state,api,modal,toast,navigate,editRecord,openKind,download,esc,fmt,pct,text,table,panel,metric,propName}) {
 const $=s=>document.querySelector(s);
 const names={room:'住宿',dining:'餐饮',water:'游乐 / 水世界',spa:'温泉 / SPA',goods:'零售与会员'};
 const views={room:'inventory',dining:'business',water:'leisure',spa:'wellness',goods:'retail'};
 const byView=Object.fromEntries(Object.entries(views).map(([k,v])=>[v,k]));
 const primary={hotel:'room',restaurant:'dining',water:'water',spa:'spa'};
 const operatingFields={dining:['available_tables','meal_periods','served_tables','waste_cost','labor_hours'],water:['visitors','daily_capacity','safety_incidents','labor_hours'],spa:['visitors','appointments','completed_appointments','available_minutes','used_minutes','labor_hours'],goods:['labor_hours']};
 const help={room:'只考核住宿：售出间夜、房价、可售房量和未来预订。套餐中的餐饮及温泉权益分别核算。',dining:'只考核餐饮：收费客单、桌台周转、食材耗用、损耗、宴会团建和食品安全。',water:'只考核游乐：实际入园、人均收入、真实营业日、核准日承载和安全事件。',spa:'只考核温泉与SPA：服务人次、同批预约完成、工位时段、人员工时和服务安全。',goods:'商品以实际交付确认收入，代销只确认净服务费；会员售卡与权益履约分别核算。'};
 function focus() {
  const s=state();if(byView[s.view])return byView[s.view];
  if(s.view!=='overview')return null;
  if(s.focusScope&&s.focusScope!=='auto')return s.focusScope;
  return primary[s.props.find(p=>p.property_id===s.property)?.data.business]||null;
 }
 function heading() {
  const key=focus();document.body.dataset.sector=key||'';
  if($('#intro'))$('#intro').textContent=key?help[key]:'各业态使用各自的经营指标，集团看收入、现金与待决策事项。';
  if(state().view==='overview'&&key)$('#page-title').textContent=(state().property?propName(state().property)+' · ':'')+names[key]+'经营';
 }
 function selector() {
  return `<div class="sector-switch"><label>首页指标侧重<select id="sector-focus"><option value="auto">${state().property?'按项目业态自动切换':'集团全业态'}</option>${Object.entries(names).map(([k,v])=>`<option value="${k}" ${state().focusScope===k?'selected':''}>${v}</option>`).join('')}</select></label><span>收入按实际履约权益归属，跨业态套餐分别分摊。</span></div>`;
 }
 function cards(key) {
  const sector=state().report.sectors[key];
  return `<div class="metrics sector-metrics" data-sector="${key}">${sector.cards.map(c=>metric(c.label,c.unit==='%'?pct(c.value):fmt(c.value),c.formula,c.kind,c.unit==='%'?'':c.unit).replace('data-metric="'+c.kind+'"',`data-sector-metric="${c.key}" data-sector-key="${key}"`)).join('')}</div>`;
 }
 function groupCards() {
  const r=state().report,m=r.metrics;
  const sectorRevenue=k=>r.sectors[k].metrics.revenue;
  return '<div class="metrics">'+[
   metric('集团净履约收入',fmt(m.revenue),'各业务权益履约收入合计，扣明确退款冲回','fulfillment','元'),
   metric('获客后经营贡献',fmt(m.contribution),'成本完整后：净履约收入 − 成本 − 获客 − 佣金','cost','元'),
   metric('期间实际到账',fmt(m.received),'银行收款 + 平台结算 − 银行退款','payment','元'),
   metric('截至期末待结算',fmt(m.pending),'平台累计净收款 − 累计银行结算','payment','元'),
   metric('住宿净履约收入',fmt(sectorRevenue('room')),'仅客房权益；住宿专业指标见住宿经营','fulfillment','元'),
   metric('餐饮净履约收入',fmt(sectorRevenue('dining')),'收费餐饮权益；赠送早餐不重复计收入','fulfillment','元'),
   metric('游乐净履约收入',fmt(sectorRevenue('water')),'实际游乐权益履约，不以售券收款代替','fulfillment','元'),
   metric('温泉 / SPA净收入',fmt(sectorRevenue('spa')),'仅温泉及SPA已履约权益，售卡另核算','fulfillment','元')].join('')+'</div>';
 }
 function groupPanels() {
  const r=state().report;
  return `<div class="sector-grid">${Object.entries(names).map(([k,n])=>{
   const d=r.sectors[k],key={room:'occupancy',dining:'average_spend',water:'visitors',spa:'appointment_completion',goods:'fulfilled_orders'}[k],c=d.cards.find(x=>x.key===key);
   return `<article class="panel sector-tile"><span class="eyebrow">${n}</span><h2>${fmt(d.metrics.revenue)} <small>元净履约收入</small></h2><p>${esc(c?.label||'业务指标')} <strong>${c?.unit==='%'?pct(c.value):fmt(c?.value)} ${c?.unit==='%'?'':esc(c?.unit||'')}</strong></p><button class="button" data-sector-view="${views[k]}">进入${n}经营 →</button></article>`;
  }).join('')}</div>`;
 }
 function chart(key) {
  const ds=state().report.sectors[key].daily,known=ds.filter(x=>x.revenue!==null);
  if(!known.length)return '<p class="muted">尚无本业态履约记录；上传营业日报不会凭空生成收入。</p>';
  const max=Math.max(...known.map(x=>Math.abs(x.revenue)),1),negative=known.some(x=>x.revenue<0),base=negative?125:200,scale=negative?85:155;
  const segments=[];let current=[];ds.forEach((d,i)=>{if(d.revenue===null){if(current.length)segments.push(current.join(' '));current=[];}else current.push(`${40+i*660/Math.max(1,ds.length-1)},${base-d.revenue/max*scale}`);});if(current.length)segments.push(current.join(' '));
  return `<svg viewBox="0 0 750 245" role="img" aria-label="${names[key]}每日净履约收入趋势">${[40,120,200].map(y=>`<line x1="40" y1="${y}" x2="700" y2="${y}" stroke="#e3e9df"/>`).join('')}<text x="40" y="20" font-size="12" fill="#7d8b77">最高绝对值 ¥${fmt(max)}</text>${segments.map(p=>`<polyline points="${p}" stroke="#367c6f" stroke-width="3" fill="none"/>`).join('')}${ds.map((d,i)=>d.revenue===null?'':`<circle cx="${40+i*660/Math.max(1,ds.length-1)}" cy="${base-d.revenue/max*scale}" r="3" fill="#367c6f"><title>${d.day}：${fmt(d.revenue)}元</title></circle>`).join('')}<text x="40" y="234" font-size="11">${ds[0].day}</text><text x="630" y="234" font-size="11">${ds.at(-1).day}</text></svg>`;
 }
 function operatingTable(key) {
  const d=state().report.sectors[key],schema=state().schemas.business_day;
  const fields=['day','is_open','complete',...(operatingFields[key]||[]).filter(k=>!(state().user.role==='operations'&&k==='waste_cost')),'source_ref','owner'];
  return panel(names[key]+'运营日报',table(['项目',...fields.map(k=>schema.fields[k].label)],d.operating_records.map(r=>[esc(propName(r._property)),...fields.map(k=>typeof r[k]==='boolean'?(r[k]?'是':'否'):esc(r[k]??'—'))])),`<span class="tag">缺少 ${d.missing_days} 个项目日；空白保留未知</span>`);
 }
 function quality(key) {
  const d=state().report.sectors[key];
  if(key==='room')return panel('住宿数据完整性',`<div class="quality-row"><span>逐日可售房量</span><b>${state().report.metrics.inventory_complete?'所选期间已齐':'待补齐'}</b></div><div class="quality-row"><span>缺失酒店日房态</span><b>${state().report.metrics.missing_inventory_days}</b></div><p class="subtle">仅住宿项目参与可售房量和预订分母，餐饮、游乐的营业数量不会被当作房间数。</p>`);
  return panel('这块业务的数据是否齐全',`<div class="quality-row"><span>营业日历</span><b>${d.calendar_complete?'所选期间已齐':'待补齐'}</b></div><div class="quality-row"><span>已登记营业项目日</span><b>${d.recorded_open_days}</b></div><div class="quality-row"><span>尚未采集的营业项目日</span><b>${d.missing_days}</b></div>${key==='dining'&&state().user.role!=='operations'?`<div class="quality-row"><span>逐日食材耗用与财务确认</span><b>${d.metrics.food_cost_complete?'已齐':'待补齐'}</b></div>`:''}<p class="subtle">报表上的“—”表示尚不能确认，不表示0。已填写的运营数量还需勾选核对；营业日报不自动生成收入或费用。</p><button class="button" data-sector-evidence="${key}">查看指标口径与数据来源</button>`);
 }
 function orders(key) {
  const d=state().report.sectors[key];
  return panel('本业务权益对应订单',table(['订单','项目','成交渠道',names[key]+'净履约收入','操作'],d.orders.map(o=>[esc(o.order_no),esc(propName(o.property_id)),esc(text(o.channel)),fmt(o.revenue),`<button class="text-button" data-drill="${o.id}">下钻整单</button>`])), '<span class="tag">本表只合计本业务权益；整单可含其他套餐权益</span>');
 }
 function rights() {
  const r=state().report;
  return panel('会员与预售券权益余额',table(['项目','业务','权益','发行份数','取消','已核销','剩余','未履约分摊额','有效期'],r.entitlements.map(x=>[esc(propName(x._property)),esc(text(x.business)),esc(x.code),fmt(x.quantity),fmt(x.cancelled_units),fmt(x.redeemed_units),fmt(x.remaining_units),fmt(x.unrecognized_allocation),x.expires_on])), '<span class="tag">售卡收款与核销收入分开，过期不自动确认收入</span>');
 }
 function render(key,{overview=false}={}) {
  const d=state().report.sectors[key];
  const actions=key==='room'?'':`<div class="section-actions"><button class="button primary" data-sector-entry="${key}">＋ 填${names[key]}日报</button><button class="button" data-sector-template="${key}">下载本业态采集模板</button><button class="button" data-kind="fulfillment">履约与套餐分摊</button>${state().user.role!=='operations'?'<button class="button" data-kind="cost">成本与耗用台账</button>':''}<button class="button" data-sector-view="automation">自动采集怎么接入 →</button></div>`;
  const products=state().report.products.filter(p=>key==='goods'?['goods','consignment_fee','membership'].includes(p.business):p.business===key);
  const groups=(key==='dining'?panel('餐饮客群 · 收费与赠送分开',table(['客群','净履约收入','收费用餐人次','赠送餐饮人次','收费客单'],d.guest_groups.map(x=>[esc(text(x.guest_type)),fmt(x.revenue),fmt(x.paid_guests),fmt(x.included_guests),fmt(x.average_spend)]))):'')+(key!=='room'?panel(names[key]+'产品 / 套餐表现',table(['项目','产品','净履约收入',...(state().user.role!=='operations'?['已分摊成本','已知差额']:[])],products.map(p=>[esc(propName(p._property)),esc(p.name),fmt(p.revenue),...(state().user.role!=='operations'?[fmt(p.allocated_cost),fmt(p.known_contribution)]:[])])),'<span class="tag">需要产品代码与实际明细，缺失不估算</span>'):'');
  return (overview?selector():'')+cards(key)+actions+`<div class="grid-main">${panel(names[key]+'净履约收入趋势',chart(key))}${quality(key)}</div>`+groups+(key==='room'?'':operatingTable(key))+(key==='goods'?rights():'')+orders(key)+panel('核算与采集口径',`<p class="muted">${esc(d.scope_note)} ${key==='dining'?'早餐配餐和收费餐饮分别统计，采购入库须经库存与实际耗用核算后才能成为食材成本。':''}${key==='water'?'入园人次来自核验；日接待上限须由项目负责人确认，停业日不计入日均收入分母。退款归属原业务，停业日冲回不伪装成开园收入。':''}</p>`);
 }
 function dictionary(key) {
  const d=state().report.sectors[key];
  modal(names[key]+'指标口径与来源',table(['指标','当前值','公式','原始记录'],d.cards.map(c=>[esc(c.label),c.unit==='%'?pct(c.value):fmt(c.value),esc(c.formula),esc(state().schemas[c.kind]?.label||c.kind)])),true);
 }
 function evidence(key,metricKey) {
  const d=state().report.sectors[key],card=d.cards.find(c=>c.key===metricKey);
  let body=card?`<p class="work-warning">${esc(card.formula)}。当前值：${card.unit==='%'?pct(card.value):fmt(card.value)} ${esc(card.unit==='%'?'':card.unit)}</p>`:'';
  if(card?.kind==='business_day')body+=operatingTable(key);
  else if(card?.kind==='inventory')body+=`<p>本期实际间夜 ${fmt(d.metrics.nights)}；客房净收入 ${fmt(d.metrics.revenue)}元；已确认可售间夜 ${fmt(d.metrics.available)}。</p>`+table(['日期','酒店','房型','可售','维修停用','锁房'],d.inventory_records.map(x=>[x.day,esc(propName(x._property)),esc(x.room_type),fmt(x.available),fmt(x.out_of_service),fmt(x.locked)]));
  else if(card?.kind==='reservation')body+=table(['日期','可售间夜','确认间夜','维修停用'],state().report.future.slice(0,card.key==='booking7'?7:30).map(x=>[x.day,fmt(x.available),fmt(x.booked),fmt(x.out_of_service)]));
  else if(card?.kind==='cost')body+=table(['日期','科目','已归属金额'],d.costs.map(x=>[x.day,esc(text(x.category)),fmt(x.amount)]));
  else if(card?.kind==='issue')body+=table(['问题','部门','严重性','负责人','期限'],state().report.issues.filter(x=>(key==='dining'?['kitchen','dining']:key==='room'?['rooms','frontdesk','cleaning']:[key]).includes(x.department)).map(x=>[esc(x.title),esc(text(x.department)),esc(text(x.severity)),esc(x.owner),x.due_date]));
  else if(card?.kind==='entitlement')body+=rights();
  else body+=table(['日期','项目','订单','权益收入','赠送','服务人次'],d.fulfillments.map(x=>[x.day,esc(propName(x._property)),esc(x.order_no),fmt(x.amount),x.included?'是':'否',fmt(x.guests)]))+table(['退款日','订单','对应权益','收入冲回'],d.refunds.map(x=>[x.day,esc(x.order_no),esc(x.fulfillment_ref),fmt(x.amount)]));
  modal(names[key]+' · '+(card?.label||'数据来源'),body,true);
 }
 function configureForm(kind,form) {
  const apply=()=>{
   const prop=state().props.find(p=>p.property_id===(form.elements._property?.value||state().property));
   if(kind==='business_day') {
    const key=form.elements.business.value,allowed=new Set(['day','business','is_open','complete',...(operatingFields[key]||[]),'source_ref','owner','note']);
    for(const el of form.querySelectorAll('[name]'))if(el.name[0]!=='_'){const show=allowed.has(el.name);el.disabled=!show;el.closest('label').hidden=!show;}
   }
   if(kind==='target'&&form.elements.occupancy){const show=!prop||prop.data.business==='hotel';form.elements.occupancy.disabled=!show;form.elements.occupancy.closest('label').hidden=!show;}
   if(kind==='fulfillment'){
    const key=form.elements.business.value;
    for(const name of ['room_nights','room_type','guest_type']){const el=form.elements[name];const show=name==='guest_type'?key==='dining':key==='room';el.closest('label').hidden=!show;if(!show)el.value=name==='room_nights'?'0':name==='guest_type'?'not_applicable':'';}
   }
  };
  if(kind==='business_day')form.elements.business.addEventListener('change',apply);
  if(kind==='fulfillment')form.elements.business.addEventListener('change',apply);
  form.elements._property?.addEventListener('change',apply);apply();
 }
 function bind() {
  if($('#sector-focus'))$('#sector-focus').onchange=e=>{state().focusScope=e.target.value;navigate('overview');};
  document.querySelectorAll('[data-sector-view]').forEach(b=>b.onclick=()=>navigate(b.dataset.sectorView));
  document.querySelectorAll('[data-sector-entry]').forEach(b=>b.onclick=()=>{
   const key=b.dataset.sectorEntry,prop=state().property||state().props.find(p=>primary[p.data.business]===key)?.property_id;
   editRecord('business_day',null,{business:key,day:state().today,is_open:true,complete:false},prop);
  });
  document.querySelectorAll('[data-sector-template]').forEach(b=>b.onclick=()=>download('/api/template/business_day?format=csv&business='+b.dataset.sectorTemplate).catch(e=>toast(e.message)));
  document.querySelectorAll('[data-sector-evidence]').forEach(b=>b.onclick=()=>dictionary(b.dataset.sectorEvidence));
  document.querySelectorAll('[data-sector-metric]').forEach(b=>b.onclick=()=>evidence(b.dataset.sectorKey,b.dataset.sectorMetric));
 }
 function automation() {
  const rows=[['住宿','PMS、门锁/夜审','房态、逐夜入住、取消、房费分摊、收退款','店长 + PMS供应商','订单/房态5–15分钟；夜审日结'],['餐饮','POS收银 + 库存/采购','账单菜品、收费/赠送人次、开台、退菜；库存与食材耗用、损耗','餐饮经理 + 财务 + POS供应商','POS实时/15分钟；耗用日结'],['游乐','售票、核销闸机、营业排班','售票与核销关联、实际入园、免费人次、开园日历、日接待上限、安全事件','项目经理 + 票务供应商','核销5–15分钟；安全/日历日结'],['温泉 / SPA','预约、排班、项目核销','服务日同批预约/完成、散客、工位可售/占用分钟、实际工时','项目负责人 + 预约系统供应商','预约5–15分钟；排班日结'],['财务','支付商户、银行、财务系统','收款、退款、净结算、平台费、工资水电、费用归属与合同','财务负责人','支付回调；银行/费用日结'],['线上运营','OTA、抖音、小红书、视频号、会员平台','授权范围曝光、咨询、成交、预约、退款、核销；保留来源及未知','运营负责人 + 平台服务商','按开放接口和授权频率']];
  return panel('自动采集：先接业务系统，再用AI补录',`<p class="muted">结构化订单和流水通过授权接口自动同步；照片与文件用OCR辅助读取。AI无法从发票推知实际入住、入园、食材耗用或银行是否到账。接入凭证不等于平台已连接，实际结果须看同步日志与对账。</p><div class="section-actions"><a class="button primary" href="./templates/data-sources.csv" download>下载数据源盘点表</a><button class="button" data-sector-view="workspace">员工拍单据 / 现场资料</button></div>`)+panel('需要各负责人准备的数据与授权',table(['板块','从哪里取','需要的数据','谁负责','建议频率'],rows.map(r=>r.map(esc))))+panel('落地顺序',`<ol class="workflow-list"><li><b>先盘点：</b>每家店填写系统名称、供应商联系人、接口/定时导出能力、账号授权范围、门店和订单编号；提供脱敏样例。</li><li><b>部署完整版：</b>正式HTTPS地址、持久数据库与附件磁盘、按岗位权限、备份及异常监控；密钥只放后端。</li><li><b>优先打通PMS + 餐饮POS + 财务：</b>建立门店、产品、订单及退款ID映射。接口应覆盖变更、取消、退款与历史回补，重复投递不得重复入账。</li><li><b>再接票务/闸机、预约、库存与营销：</b>没有API时由供应商提供定时文件投递；员工拍照作为补充，复杂票据交财务核对。</li><li><b>一家店试运行：</b>逐日比对原系统、支付、已履约收入和驾驶舱明细；对账通过后推广。财务保留费用确认与成本完整性审核。</li></ol><p class="work-warning">当前包含可用的签名接入入口和本地OCR；尚未配置任何真实供应商的自动同步程序。录音只保存回放，不自动转写。</p>`);
 }
 return {focus,heading,selector,cards,groupCards,groupPanels,chart,render,dictionary,configureForm,bind,automation,views,byView};
}
