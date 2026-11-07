export function createCommerce({state,modal,toast,navigate,editRecord,openKind,esc,fmt,pct,text,table,panel,metric,propName}) {
 const $=s=>document.querySelector(s);
 const modes={self:'自营产品',joint:'联营产品',affiliate:'电商带货',retail:'零售产品',other:'其他合作'};
 const labels={gross:'全额销售收入',net:'净佣金 / 服务费',unconfirmed:'待合同确认',platform:'平台代收',supplier:'商家直收',shipping:'物流交付',pickup:'门店自提',redeem:'实际核销',service:'服务完成',physical:'实物',voucher:'券类权益'};
 const financial=()=>state().user.role!=='operations';
 const isFinance=()=>['admin','finance'].includes(state().user.role);
 const definitions=[
  ['paid_gmv','支付成交GMV','元','期间客户实际支付交易额，含商家直收；不是平台收入'],
  ['paid_orders','支付订单','单','期间支付事件按项目与订单去重，多行商品只算一单'],
  ['average_order','支付客单价','元/单','支付成交GMV ÷ 支付订单数'],
  ['paid_net','期间支付净额','元','期间客户支付 − 期间客户退款；退款可来自历史订单'],
  ['recognized_income','平台已履约净收入','元','全额合同按交付收入，净额合同按已核实佣金/服务费，扣收入冲回'],
  ['contribution','成本核对后经营贡献','元','已履约净收入 − 直接/公共已登记费用及结算扣费；成本完整才显示'],
  ['cohort_refund_rate','同批支付订单退款率','%','期间发生支付的订单中，截至期末已有退款的订单占比'],
  ['timely_shipping','按约准时发货率','%','已到发货期限的物流订单行，按时足量发货行数 ÷ 到期行数']
 ];
 const l=v=>labels[v]||modes[v]||text(v);
 function headline(){const d=state().report.commerce,m=d.metrics;return `<div class="metrics commerce-metrics">${definitions.filter(([key])=>key in m).map(([key,label,unit,formula])=>metric(label,unit==='%'?pct(m[key]):fmt(m[key]),formula,'commerce_event',unit==='%'?'':unit).replace('data-metric="commerce_event"',`data-commerce-metric="${key}"`)).join('')}</div>`;}
 function sourceTable(){const d=state().report.commerce;return table(['日期','订单 / 行','事件','客户交易/资金额',...(financial()?['平台收入确认/冲回','合作方款变动','结算扣费']:[]),'凭证'],d.events.map(e=>[e.day,esc(e.order_no+' / '+e.line_no),esc(text(e.type)),fmt(e.amount),...(financial()?[fmt(e.recognized_amount),fmt(e.supplier_amount),fmt(e.fee_amount)]:[]),esc(e.source_ref)]));}
 function productTable(){const d=state().report.commerce;return panel('商品与产品表现 · 不限于实物',table(['SKU / 产品','模式','品类','形态','合作方','支付GMV','履约数量',...(financial()?['平台净收入','已核对直接贡献']:[])],d.products.slice().sort((a,b)=>(b.paid_gmv||0)-(a.paid_gmv||0)).map(p=>[esc(p.name)+'<small class="cell-text">'+esc(p.code)+'</small>',esc(l(p.mode)),esc(p.category||'未分类'),esc(l(p.product_type)),esc(p.supplier||'—'),fmt(p.paid_gmv),fmt(p.fulfilled_quantity)+' '+esc(p.unit),...(financial()?[fmt(p.recognized_income),fmt(p.direct_contribution)]:[])])), '<span class="tag">SKU金额来自订单行，参考售价不代替成交价</span>');}
 function orders(mode=''){
  const rows=state().report.commerce.lines.filter(x=>!mode||x.mode===mode);
  return table(['订单 / 行','商品','经营模式','收入方式','履约方式','状态','本期支付','本期退款',...(financial()?['本期平台净收入','直接成本完整']:[]),'操作'],rows.map(x=>[esc(x.order_no+' / '+x.line_no),esc(x.product_name),esc(l(x.mode)),esc(l(x.recognition)),esc(l(x.delivery)),esc(text(x.status)),fmt(x.paid_gross),fmt(x.refund_amount),...(financial()?[fmt(x.recognized_income),x.cost_complete===true?'已核对':'待核对']:[]),`<button class="text-button" data-commerce-line="${x._id}">查看来源</button>`]));
 }
 function render(){
  const d=state().report.commerce,m=d.metrics;
  const actions=[['commerce_product','商品与合作目录'],['commerce_line','订单行与合同口径'],['commerce_event','支付 / 履约 / 结算事件'],...(financial()?[['commerce_cost','成本与投放'],['coverage','财务完整性确认']]:[]),['commerce_traffic','访问批次'],['commerce_stock','库存快照']];
  const liquidity=financial()?panel('资金、佣金与合作方 · 截至所选期末',table(['指标','金额','口径'],[
   ['期间平台收退款净到账',fmt(m.received),'本方银行收退款、渠道净结算、佣金收退；不是平台收入'],
   ['渠道待结算余额',fmt(m.pending_channel),'累计渠道支付 − 渠道退款 − 银行结算及扣费；负数保留为待补退款资金'],
   ['待收佣金',fmt(m.commission_pending),'商家直收订单已确认佣金 − 累计收到佣金'],
   ['已收需退佣金',fmt(m.commission_returnable),'退款后应退已收佣金，不隐藏为0'],
   ['已登记合作方待付',fmt(m.supplier_payable),'代收本金/采购应付 − 冲回 − 已支付'],
   ['合作方待追偿',fmt(m.supplier_recovery),'已支付合作方款后发生退款形成的已登记追偿余额']])):'';
  return `<div class="commerce-banner"><div><span class="eyebrow">SENHUO SELECT</span><h2>森活优选 · 线上产品经营</h2><p>自营、联营、带货、零售及其他合作分别分析；商品、券和服务按真实履约确认。</p></div><span class="tag">${state().readOnly?'模拟数据 · 只读体验':state().dataset==='demo'?'独立模拟空间':'真实业务空间'}</span></div>`+headline()+`<div class="section-actions">${actions.map(([kind,title])=>`<button class="button" data-commerce-open="${kind}">${title}</button>`).join('')}<button class="button primary" data-commerce-new="commerce_line">＋ 新增订单行</button><button class="button" data-commerce-new="commerce_product">＋ 新增商品</button></div>`+
   panel('按经营模式分析',table(['模式','支付GMV','支付订单','客户退款',...(financial()?['已履约净收入','已登记直接成本','模式直接贡献']:[])],d.modes.map(x=>[esc(x.label),fmt(x.paid_gmv),fmt(x.paid_orders),fmt(x.refunds),...(financial()?[fmt(x.recognized_income),fmt(x.direct_cost),fmt(x.direct_contribution)]:[])])),'<span class="tag">一单可含多种模式，模式订单数不相加；直接贡献未扣未分摊公共费用</span>')+
   `<div class="grid-two">${panel('流量、转化与投放',table(['指标','值','口径'],[
    ['日渠道UV合计',fmt(m.daily_uv_sum),'各日各渠道去重访客合计，不冒充跨日去重人数'],
    ['访问批次支付转化',pct(m.visitor_conversion),'同批支付人数 / 同批访客，按日渠道批次加权；窗口完整才显示'],
    ...(financial()?[['已登记广告花费',fmt(m.advertising_spend),'成本与投放台账中明确登记的广告费用'],['已归因活动ROAS',fmt(m.attributed_roas),'有匹配活动代码的付费订单成交额 / 活动花费；不是利润ROI']]:[]),
    ['在售SKU数',fmt(m.active_skus),'已登记并启用商品目录'],['在售SKU动销率',pct(m.active_sku_rate),'本期实际履约的在售SKU / 已登记在售SKU']]))}${panel('履约及数据待办',`<div class="quality-row"><span>合同收入方式待确认</span><b>${m.unconfirmed_lines}</b></div><div class="quality-row"><span>物流行缺约定发货日</span><b>${d.unknown_shipping_due}</b></div><div class="quality-row"><span>自有库存未登记SKU</span><b>${m.missing_stock}</b></div>${financial()?`<div class="quality-row"><span>缺失平台日成本确认</span><b>${d.missing_cost_days}</b></div><div class="quality-row"><span>成本整体口径</span><b>${m.cost_complete?'已确认':'待财务核对'}</b></div>`:''}<p class="subtle">发货不等于已交付，卖券不等于已核销。未知值不补0；退款发生在原订单所属模式。</p>`)}</div>`+
   panel('成交渠道对比',table(['渠道','支付GMV','支付订单','客户退款',...(financial()?['平台净收入']:[])],d.channels.map(x=>[esc(text(x.channel)),fmt(x.paid_gmv),fmt(x.paid_orders),fmt(x.refunds),...(financial()?[fmt(x.recognized_income)]:[])])))+
   productTable()+liquidity+
   panel('合作结算与未结订单',table(['订单 / 行','收款方','约定结算日',...(financial()?['渠道余额','佣金待收 / 应退','合作方待付 / 追偿']:[]),'账期'],d.lines.filter(x=>financial()&&(Math.abs(x.pending_channel||0)>.01||Math.abs(x.commission_balance||0)>.01||Math.abs(x.supplier_balance||0)>.01)).map(x=>[esc(x.order_no+' / '+x.line_no),esc(l(x.collector)),x.settle_due||'未登记',fmt(x.pending_channel),fmt(x.commission_balance),fmt(x.supplier_balance),x.settlement_overdue?'已逾期':x.settle_due?'按约跟进':'账期待确认'])))+
   panel('自有库存与缺货',table(['SKU','名称','可售数量','单位','快照日期','来源'],d.stock.map(x=>[esc(x.code),esc(x.name),fmt(x.available),esc(x.unit),x.snapshot_day||'未登记',esc(x.source_refs.join('、'))])),'<span class="tag">只统计已声明归平台的实物库存；商家库存不当作平台库存</span>')+
   panel('订单与履约来源',`<label class="block-label">订单表模式筛选<select id="commerce-mode"><option value="">全部模式</option>${Object.entries(modes).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label><div id="commerce-orders">${orders()}</div><p class="subtle">订单表列本期活动及截至期末的历史订单；顶部指标按各自发生日统计，结算余额不随下单日期丢失。</p>`)+
   panel('核算边界',`<p class="muted">${esc(d.note)} 自营与零售是否全额确认、联营是否净额确认以实际合同和主要责任判断为准；带货不把商家成交额全额当作平台收入。平台扣费在结算事件登记一次。当前未自动连接抖音、小程序、电商店铺或供应商系统。</p>`);
 }
 function bindLines(){document.querySelectorAll('[data-commerce-line]').forEach(b=>b.onclick=()=>{
   const row=state().report.commerce.lines.find(x=>x._id===Number(b.dataset.commerceLine));
   const events=state().report.commerce.events.filter(e=>e._property===row._property&&e.order_no===row.order_no&&e.line_no===row.line_no);
   modal('森活优选订单 · '+row.order_no+' / '+row.line_no,table(['项目','内容'],[['商品',esc(row.product_name)],['经营模式',esc(l(row.mode))],['收入方式',esc(l(row.recognition))],['收款方',esc(l(row.collector))],['履约方式',esc(l(row.delivery))],['关联园区订单',esc(row.park_property&&row.park_order?row.park_property+' / '+row.park_order:'无关联')]])+table(['日期','事件','金额','数量',...(financial()?['确认/冲回收入','合作方金额']:[]),'原始依据'],events.map(e=>[e.day,esc(text(e.type)),fmt(e.amount),fmt(e.quantity),...(financial()?[fmt(e.recognized_amount),fmt(e.supplier_amount)]:[]),esc(e.source_ref)]))+'<p class="subtle">本平台记录不会自动再生成一笔园区订单。</p>',true);
  });}
 function bind(){
  document.querySelectorAll('[data-commerce-open]').forEach(b=>b.onclick=()=>{const p=state().props.find(p=>p.data.business==='commerce');if(!p)return toast('当前账号未获森活优选项目授权');if(!state().property){state().property=p.property_id;$('#property-filter').value=p.property_id;}openKind(b.dataset.commerceOpen);});
  document.querySelectorAll('[data-commerce-new]').forEach(b=>b.onclick=()=>{
   const p=state().props.find(p=>p.data.business==='commerce');if(!p)return toast('当前账号未获森活优选项目授权');
   const kind=b.dataset.commerceNew,prefill=kind==='commerce_line'?{order_date:state().today,mode:'self',traffic:'unknown',channel:'unknown',recognition:'unconfirmed',collector:'unconfirmed',delivery:'shipping',status:'confirmed',cost_complete:false,owner:state().user.username}:{mode:'self',product_type:'physical',owned_stock:false,active:true,unit:'件',owner:state().user.username};
   editRecord(kind,null,prefill,p.property_id);
  });
  if($('#commerce-mode'))$('#commerce-mode').onchange=e=>{$('#commerce-orders').innerHTML=orders(e.target.value);bindLines();};bindLines();
  document.querySelectorAll('[data-commerce-metric]').forEach(b=>b.onclick=()=>{const def=definitions.find(x=>x[0]===b.dataset.commerceMetric);modal('森活优选 · '+def[1],`<p class="work-warning">${esc(def[3])}</p>`+sourceTable(),true);});
 }
 function configureForm(kind,form){
  if(kind==='commerce_product'){
   const apply=()=>{if(form.elements.mode.value==='affiliate'||form.elements.product_type.value!=='physical')form.elements.owned_stock.value='false';};
   form.elements.mode.addEventListener('change',apply);form.elements.product_type.addEventListener('change',apply);apply();
  }
  if(kind==='commerce_line'&&!isFinance()){
   form.elements.cost_complete.disabled=true;form.elements.cost_complete.closest('label').hidden=true;
   const current=form.elements.recognition.value;
   for(const option of form.elements.recognition.options)option.disabled=option.value!=='unconfirmed'&&option.value!==current;
  }
 }
 function tile(){const m=state().report.commerce.metrics;return `<article class="panel commerce-home-tile"><div><span class="eyebrow">独立线上经营</span><h2>森活优选</h2><p>支付成交GMV <b>${fmt(m.paid_gmv)}</b> 元${financial()?' · 平台已履约净收入 <b>'+fmt(m.recognized_income)+'</b> 元':''}</p><p class="subtle">自营 / 联营 / 电商带货 / 零售；GMV不重复加入园区收入。</p></div><button class="button primary" data-open-commerce>进入森活优选 →</button></article>`;}
 return {render,bind,configureForm,tile};
}
