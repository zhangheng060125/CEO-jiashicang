// GitHub Pages serves read-only synthetic snapshots; normal deployments keep their API.
export const isStaticPreview=location.hostname.endsWith('.github.io')||window.SENHUO_STATIC_PREVIEW===true;
const base=new URL('./',import.meta.url);
const cached=new Map();
let signedIn=false;
try{signedIn=sessionStorage.getItem('senhuo-static-session')==='demo';}catch{}
function session(value){signedIn=value;try{value?sessionStorage.setItem('senhuo-static-session','demo'):sessionStorage.removeItem('senhuo-static-session');}catch{}}
async function asset(name){
 if(!cached.has(name))cached.set(name,fetch(new URL('demo/'+name+'?v=1.6.0',base),{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error('演示快照尚未发布，请稍后刷新。');return r.json();}).catch(e=>{cached.delete(name);throw e;}));
 return cached.get(name);
}
function json(value,status=200){return new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});}
const deny=message=>json({detail:message},403);
async function records(kind,prop){const rows=await asset('records.json');return rows.filter(r=>(!kind||r.kind===kind)&&(!prop||r.property_id===prop));}

export async function request(url,options={}){
 if(!isStaticPreview)return fetch(url,options);
 try{
  const u=new URL(url,location.origin),path=u.pathname,method=(options.method||'GET').toUpperCase();
  if(path==='/api/preview-info'&&method==='GET'){
   const m=await asset('manifest.json');return json({enabled:true,ready:true,start:m.start,end:m.end,asof:m.asof,read_only:true});
  }
  if(path==='/api/login'&&method==='POST'){
   let body;try{body=JSON.parse(options.body);}catch{return json({detail:'请求格式无效'},400);}
   if(body?.demo!==true)return deny('此网站提供只读演示；正式账号需在已部署后台的系统中登录。');
   await asset('manifest.json');session(true);return json({ok:true});
  }
  if(path==='/api/logout'&&method==='POST'){session(false);return json({ok:true});}
  if(!signedIn)return json({detail:'请先点击开始预览体验'},401);
  if(method!=='GET')return deny('GitHub Pages为只读演示，录入、修改和整改保存需连接完整版后台。');
  if(u.searchParams.has('dataset')&&u.searchParams.get('dataset')!=='demo')return deny('只读演示不能访问真实经营数据。');
  const m=await asset('manifest.json');
  if(path==='/api/me')return json({username:'演示访客',role:'admin',properties:['*'],demo:true,read_only:true});
  if(path==='/api/schema')return json({schemas:await asset('schema.json'),writable:[],today:m.asof,read_only:true});
  if(path==='/api/workspace/config')return json({recognition:{engine:'demo_snapshot',available:false,chinese_ready:false,external_ai:false},max_file_mb:64,max_files:5,manage:false,book:false,direct:false});
  if(path==='/api/workspace/items'){
   const value=await asset('workspace.json'),prop=u.searchParams.get('property_id');
   return json({items:value.items.filter(x=>!prop||x.property_id===prop)});
  }
  if(/^\/api\/workspace\/items\/\d+$/.test(path)){
   const value=await asset('workspace.json'),item=value.items.find(x=>x.id===Number(path.split('/').at(-1)));
   return item?json(item):json({detail:'演示记录不存在'},404);
  }
  if(path==='/api/dashboard'){
   const prop=u.searchParams.get('property_id')||'',end=u.searchParams.get('end')||m.end,start=u.searchParams.get('start')||m.start;
   const days=Math.round((Date.parse(end)-Date.parse(start))/86400000)+1;
   if(end!==m.end||!m.periods.includes(days)||start!==new Date(Date.parse(end)-(days-1)*86400000).toISOString().slice(0,10))return json({detail:'只读演示支持最近7天或30天，请选择预设期间或恢复默认视图。'},422);
   const file=m.reports[`${prop||'all'}:${days}`];if(!file)return json({detail:'没有对应项目的演示快照'},404);
   return json(await asset(file));
  }
  if(path.startsWith('/api/records/')){
   const kind=path.split('/').at(-1),schemas=await asset('schema.json');
   if(!Object.hasOwn(schemas,kind))return json({detail:'未知数据类型'},404);
   return json({records:(await records(kind,u.searchParams.get('property_id'))).filter(r=>!u.searchParams.get('business')||r.data.business===u.searchParams.get('business'))});
  }
  if(/^\/api\/order\/\d+$/.test(path)){
   const rows=await records(),order=rows.find(r=>r.kind==='order'&&r.id===Number(path.split('/').at(-1)));
   if(!order)return json({detail:'示例订单不存在'},404);
   return json({order,records:rows.filter(r=>r.property_id===order.property_id&&r.data.order_no===order.data.order_no)});
  }
  if(path==='/api/logs')return json({imports:[],audit:[]});
  return deny('此功能需要连接完整版后台。');
 }catch(e){return json({detail:e.message},503);}
}

export async function download(url){
 if(!isStaticPreview){location.href=url;return;}
 if(!signedIn)throw Error('请先进入预览体验');
 const u=new URL(url,location.origin),kind=u.pathname.split('/').at(-1),schemas=await asset('schema.json');
 if(!Object.hasOwn(schemas,kind))throw Error('没有对应模板');
 if(u.pathname.startsWith('/api/template/')){
  const a=document.createElement('a'),xlsx=u.searchParams.get('format')==='xlsx';
  const sector=kind==='business_day'&&['dining','water','spa','goods'].includes(u.searchParams.get('business'))?'-'+u.searchParams.get('business'):'';a.href=new URL(xlsx?'templates/all-templates.xlsx':`templates/${kind}${sector}.csv`,base);a.download=xlsx?'all-templates.xlsx':`${kind}${sector}.csv`;a.click();return;
 }
 if(!u.pathname.startsWith('/api/export/'))throw Error('此下载需要后台');
 if(u.searchParams.get('dataset')!=='demo')throw Error('只允许导出演示记录');
 const start=u.searchParams.get('start'),end=u.searchParams.get('end');
 const rows=(await records(kind,u.searchParams.get('property_id'))).filter(r=>{if(u.searchParams.get('business')&&r.data.business!==u.searchParams.get('business'))return false;const d=r.data.day||r.data.order_date;return !d||(!start||d>=start)&&(!end||d<=end);});
 const fields=Object.keys(schemas[kind].fields),header=['property_id','external_id',...fields,'version','updated_at'];
 function cell(v){if(v==null)v='';if(typeof v==='string'&&/^[=+\-@\t\r]/.test(v))v="'"+v;return '"'+String(v).replaceAll('"','""')+'"';}
 const csv=[header,...rows.map(r=>[r.property_id,r.external_id,...fields.map(k=>r.data[k]),r.version,r.updated_at])].map(r=>r.map(cell).join(',')).join('\r\n');
 const href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));
 const a=document.createElement('a');a.href=href;a.download=`demo-${kind}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(href),1000);
}
