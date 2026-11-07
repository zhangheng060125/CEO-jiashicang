import {isStaticPreview} from './transport.js?v=1.4.0';
// Preview navigation and explanations; business data continues to come from the API.
export function createPreview({api, modal, toast, state, navigate, openOrder, logout}) {
 const $=s=>document.querySelector(s);
 const steps=[
  {title:'看清经营全貌',view:'overview',text:'查看履约收入、入住率、ADR和RevPAR。点击指标卡可追溯原始记录；成本未齐时，经营贡献会保留未知。',action:'查看首页指标'},
  {title:'追溯一笔订单',view:'orders',text:'打开订单，核对预约、逐日履约、套餐分摊和资金记录。支付、服务和到账使用不同记录。',action:'打开示例订单',order:true},
  {title:'掌握未来房态',view:'inventory',text:'查看未来7、30、90天的确认预约、可售、锁房及维修。未预约券承诺单列，不当作已确认预订。',action:'查看房态与预订'},
  {title:'判断渠道贡献',view:'channels',text:'比较渠道带来的履约收入与获客费用，区分自然和付费流量。未知来源保留未知，聚合曝光不冒充逐客转化。',action:'比较经营渠道'},
  {title:'核对资金与结算',view:'finance',text:'查看收款、退款、预收、到账和待结算。运营公司佣金单独核算，不重复增加园区收入。',action:'查看资金核对'},
  {title:'把异常变成行动',view:'issues',text:'选择一项预警，指派负责人和截止日期，再填写整改证据与复查结果。也可以在数据中心试用录入和导入。',action:'体验异常整改'}
 ];
 let info=null,step=0,completed=false,busy=false;
 function isDemo(){return state().user?.demo===true;}
 function save(){try{sessionStorage.setItem('senhuo-preview-guide',JSON.stringify({step,completed}));}catch{}}
 function restore(){try{const v=JSON.parse(sessionStorage.getItem('senhuo-preview-guide'));if(Number.isInteger(v?.step)&&v.step>=0&&v.step<steps.length){step=v.step;completed=v.completed===true;}}catch{}}
 function showLogin(){if(isStaticPreview){modal('正式使用说明','<p class="muted">当前网址为GitHub Pages只读演示，无法运行Python后台。正式使用需要部署应用和数据库，再通过正式系统登录。</p><a class="button" href="https://github.com/zhangheng060125/CEO-jiashicang#启动" target="_blank" rel="noopener">查看源码与启动说明 →</a>');return;} $('#preview-landing').hidden=true;$('#login-form').hidden=false;$('#login-screen').hidden=false;$('#shell').hidden=true; }
 function showLanding(formalSession=false){
  $('#login-screen').hidden=false;$('#shell').hidden=true;$('#login-form').hidden=true;$('#preview-landing').hidden=false;
  const available=info?.enabled&&info?.ready;
  $('#preview-enter').disabled=!available;
  $('#preview-availability').textContent=!info?.enabled?'当前部署未开放体验，请使用正式账号登录。':!info.ready?'演示数据尚未准备，请联系管理员初始化。':`演示数据期间：${info.start} 至 ${info.end}。可自由浏览、下钻和试用演示操作。${formalSession?'进入体验将切换当前浏览器的登录状态，返回正式空间需重新登录。':''}`;
 }
 async function initialize(){
  try{info=await api('/api/preview-info');}catch{info={enabled:false};}
  $('#login-demo').hidden=!info.enabled;
  if(isStaticPreview){$('#preview-back').textContent='正式系统与部署说明';$('#preview-disclaimer')?.setAttribute('data-static','true');$('#preview-period-wrap').hidden=false;$('#start-date').readOnly=true;$('#end-date').readOnly=true;$('#preview-link').href='?preview=1';$('#preview-period').onchange=e=>{const end=new Date(info.end+'T00:00:00Z'),start=new Date(end);start.setUTCDate(start.getUTCDate()-Number(e.target.value)+1);$('#start-date').value=start.toISOString().slice(0,10);$('#end-date').value=info.end;$('#refresh').click();};}
  $('#demo-login').disabled=!info.ready;
  $('#preview-back').onclick=showLogin;
  if(isStaticPreview)$('#preview-landing .preview-disclaimer').textContent='只读演示：支持浏览、筛选、订单下钻和模板下载。全部为模拟数据；录入、修改及整改保存需要连接完整版后台。';
  if(info.enabled&&!info.ready)$('#demo-entry-note').textContent='演示数据尚未准备，请联系管理员初始化。';
  restore();
 }
 function onBoot(){
  $('#preview-toolbar').hidden=!isDemo();
  $('#preview-link').hidden=isDemo()||!info?.enabled;
  if(!isDemo())return;
  if(info?.ready){
   $('#start-date').value=info.start;$('#end-date').value=info.end;
   state().previewAsOf=info.asof;
  }
  render();
 }
 async function go(index,{perform=false}={}){
  if(busy||!isDemo())return;
  busy=true;
  try{
   step=index;completed=false;save();render();
   await navigate(steps[step].view);
   if(perform&&steps[step].order)await openOrder();
  }catch(e){toast(e.message);}finally{busy=false;render();}
 }
 function render(){
  if(!isDemo())return;
  const item=isStaticPreview&&step===5?{...steps[step],text:'查看异常证据、负责人、期限和整改处理流程。当前为只读体验，实际指派与复查保存需要运行完整版后台。',action:'查看异常与流程'}:steps[step];
  $('#preview-toolbar').innerHTML=`<div class="preview-bar-heading"><div><span class="preview-badge">预览体验</span><strong>${isStaticPreview?'GitHub Pages · 只读体验':'演示数据 · 非集团经营实绩'}</strong><p>演示基准日 ${info?.asof||state().today}，未来房态与账期按该日起算。${isStaticPreview?'当前使用预先计算的模拟快照，不接收真实资料、不保存业务修改。':'试用操作保存在共享演示空间，请使用虚构信息。'}</p></div><div class="preview-controls"><button class="button" id="preview-guide">体验路线</button><button class="text-button" id="preview-reset">恢复默认视图</button><button class="text-button" id="preview-exit">结束体验</button></div></div><div class="preview-step"><div><span class="preview-step-count">${completed?'导览已完成':`第 ${step+1} / ${steps.length} 步`}</span><h2>${completed?'继续自由探索驾驶舱':item.title}</h2><p>${completed?'你可以继续切换酒店、查询订单、查看各业务模块，或重新开始导览。':item.text}</p></div><div class="preview-step-actions">${!completed&&step>0?'<button class="button" id="preview-previous">上一步</button>':''}<button class="button" id="preview-action">${completed?'重新体验':item.action}</button>${!completed?`<button class="button primary" id="preview-next">${step===steps.length-1?'完成导览':'下一步 →'}</button>`:''}</div></div><div class="preview-progress" role="progressbar" aria-label="体验导览进度" aria-valuemin="0" aria-valuemax="${steps.length}" aria-valuenow="${completed?steps.length:step}"><span style="width:${(completed?1:step/steps.length)*100}%"></span></div>`;
  $('#preview-guide').onclick=guide;
  $('#preview-reset').onclick=reset;
  $('#preview-exit').onclick=async()=>{try{await logout();showLanding();}catch(e){toast(e.message);}};
  if($('#preview-previous'))$('#preview-previous').onclick=()=>go(step-1);
  $('#preview-action').onclick=()=>go(completed?0:step,{perform:!completed});
  if($('#preview-next'))$('#preview-next').onclick=()=>{if(step===steps.length-1){completed=true;save();render();toast('导览已完成，可继续自由体验');}else go(step+1);};
  $('#preview-toolbar').querySelectorAll('button').forEach(b=>b.disabled=busy);
 }
 function guide(){
  modal('预览体验路线',`<p class="muted">约3分钟了解经营闭环。所有数值均为模拟，演示会话不能读取或修改真实经营数据。</p><div class="preview-route-list">${steps.map((x,i)=>`<button class="preview-route" data-preview-step="${i}"><span>${String(i+1).padStart(2,'0')}</span><div><strong>${x.title}</strong><p>${x.text}</p></div><b>→</b></button>`).join('')}</div>`,true);
  document.querySelectorAll('[data-preview-step]').forEach(b=>b.onclick=()=>{$('#modal').close();go(Number(b.dataset.previewStep));});
 }
 async function reset(){
  if(busy)return;
  const s=state();s.property='';if(isStaticPreview)$('#preview-period').value='30';$('#property-filter').value='';
  if(info?.ready){$('#start-date').value=info.start;$('#end-date').value=info.end;s.previewAsOf=info.asof;}
  await go(0);toast('已恢复默认日期、经营范围和导览，已保存的演示记录仍保留');
 }
 function clear(){
  $('#preview-toolbar').hidden=true;$('#preview-link').hidden=true;step=0;completed=false;save();
 }
 return {initialize,onBoot,showLanding,showLogin,clear,guide,isPreviewPath:()=>isStaticPreview||new URLSearchParams(location.search).get('preview')==='1'||location.pathname.replace(/\/$/,'')==='/preview'};
}
