"""森活森动经营驾驶舱：SQLite persistence, scoped API and deterministic accounting."""
import os, json, sqlite3, secrets, hashlib, hmac, csv, io, math, calendar
import business
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, Response
from openpyxl import load_workbook, Workbook

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('HOTEL_DATA_DIR',ROOT/'.runtime')); DATA.mkdir(exist_ok=True,parents=True,mode=0o700); DATA.chmod(0o700)
DB=DATA/'hotel.sqlite3'
TODAY=lambda: datetime.now(timezone(timedelta(hours=8))).date().isoformat()
NOW=lambda: datetime.now(timezone.utc).isoformat()
# field: [label, type, required, options/default/help]
def f(label,typ='text',required=True,options=None): return dict(label=label,type=typ,required=required,options=options)
SCHEMAS={
 'property':dict(label='酒店与项目',fields={'code':f('项目代码'),'name':f('名称'),'business':f('业务','select',True,['hotel','restaurant','water','spa','other']),'status':f('开放状态','select',True,['unconfirmed','open','seasonal','planning','closed']),'planned_rooms':f('规划房量','integer',False),'physical_rooms':f('物理房量','integer',False),'note':f('待确认背景','text',False)}),
 'inventory':dict(label='逐日房态 / 营业日历',fields={'day':f('日期','date'),'room_type':f('房型 / 项目','text'),'physical':f('当日物理房量','integer'),'out_of_service':f('维修停用','integer'),'available':f('当日可售房量','integer'),'locked':f('锁房（可售内保留）','integer'),'voucher_commitment':f('未预约券承诺','integer'),'is_open':f('实际营业','bool'),'day_type':f('日类型','select',True,['workday','weekend','holiday']),'rate':f('参考房价','number',False)}),
 'order':dict(label='订单',fields={'order_no':f('订单号'),'order_date':f('下单日期','date'),'checkin':f('服务开始日','date'),'checkout':f('结束日（住宿离店日）','date'),'kind':f('订单类型','select',True,['stay','dining','water','spa','voucher','membership','goods','consignment','other']),'status':f('订单状态','select',True,['confirmed','completed','cancelled']),'booking_amount':f('交易额（退款前）','number'),'customer_code':f('客户匿名编号','text',False),'channel':f('最终成交渠道','select',True,['unknown','douyin','xiaohongshu','wechat','ctrip','meituan','dianping','miniapp','private','offline','other']),'discovery':f('首次发现来源','text',False),'assist':f('辅助影响来源','text',False),'traffic':f('流量属性','select',True,['unknown','organic','paid']),'campaign_code':f('营销活动编号','text',False),'contract_code':f('结算合同代码','text',False),'owner':f('跟进负责人','text',False),'principal_amount':f('代销应付货主本金（非代销留空）','number',False)}),
 'reservation':dict(label='每日预约',fields={'order_no':f('订单号'),'day':f('入住夜日期','date'),'room_type':f('房型'),'rooms':f('预订房间数','integer'),'status':f('预约状态','select',True,['confirmed','cancelled'])}),
 'fulfillment':dict(label='履约与套餐分摊',fields={'order_no':f('订单号'),'day':f('履约日期','date'),'business':f('收入业务','select',True,['room','dining','water','spa','goods','consignment_fee','membership','other']),'amount':f('本权益已履约收入','number'),'room_nights':f('实际售出间夜','integer'),'included':f('房费内赠送权益（收入必须为0）','bool'),'guest_type':f('餐饮客群','select',True,['not_applicable','resident','walkin','banquet','team']),'guests':f('用餐/服务人数','integer',False),'room_type':f('客房房型（未知留空）','text',False)}),
 'payment':dict(label='收款 / 退款 / 到账',fields={'order_no':f('订单号'),'day':f('发生日期','date'),'type':f('资金类型','select',True,['collection','refund','settlement','principal_payout','platform_fee']),'destination':f('资金位置','select',True,['platform','bank']),'amount':f('金额','number'),'revenue_reversal':f('退款中冲减已履约收入','number'),'due_date':f('预计结算日期','date',False),'principal_reversal':f('退款中冲减货主本金（非代销留空）','number',False)}),
 'cost':dict(label='经营成本',fields={'day':f('归属日期','date'),'category':f('成本科目','select',True,['payroll','utilities','food','supplies','laundry','repair','marketing','rent','fixed','other']),'amount':f('金额（未知可留空）','number',False),'scope':f('费用归属','select',True,['park','operator']),'order_no':f('关联订单（可空）','text',False),'note':f('说明','text',False),'business':f('归属业务（空为未分摊）','select',False,['room','dining','water','spa','goods','consignment_fee','membership','other'])}),
 'coverage':dict(label='成本完整性确认',fields={'day':f('归属日期','date'),'complete':f('全部成本已录入','bool'),'owner':f('确认负责人'),'note':f('缺失项目 / 口径','text',False)}),
 'contract':dict(label='运营结算合同',fields={'code':f('合同代码'),'start':f('生效日','date'),'end':f('到期日','date'),'rate':f('佣金比例（0至1）','number'),'basis':f('计佣依据','select',True,['fulfilled','paid_net']),'beneficiary':f('收款方','select',True,['operator','external']),'settlement_days':f('结算账期天数','integer'),'note':f('实际合同说明','text',False)}),
 'operator_entry':dict(label='运营公司独立账',fields={'day':f('日期','date'),'type':f('项目','select',True,['service_revenue','goods_revenue','membership_fulfilled','commission_received','commission_expense']),'amount':f('金额','number'),'contract_code':f('关联合同','text',False),'note':f('说明（不计园区交易额）','text',False)}),
 'campaign':dict(label='内容 / 直播 / 获客',fields={'code':f('活动编号'),'day':f('日期','date'),'channel':f('渠道'),'format':f('内容形式','select',True,['video','live','creator','ads','ota','miniapp','private']),'traffic':f('流量属性','select',True,['organic','paid','unknown']),'impressions':f('曝光次数','integer',False),'viewers':f('观看人数','integer',False),'consultations':f('有效咨询人数','integer',False),'spend':f('获客花费（计入贡献，不再重复录营销成本）','number',False),'owner':f('负责人','text',False)}),
 'customer':dict(label='客户与咨询',fields={'code':f('匿名客户编号'),'phone_last4':f('手机号末4位（仅脱敏存储）','text',False),'day':f('咨询日期','date'),'owner':f('跟进负责人'),'response_minutes':f('首次响应分钟','number',False),'reason':f('未成交原因','text',False),'status':f('跟进状态','select',True,['new','following','converted','lost'])}),
 'issue':dict(label='SOP 与异常整改',fields={'day':f('发现日','date'),'department':f('部门','select',True,['frontdesk','rooms','dining','cleaning','kitchen','finance','marketing','data']),'title':f('问题 / 检查项'),'severity':f('严重性','select',True,['normal','major','redline']),'order_no':f('关联订单','text',False),'evidence':f('发现证据 / 原始记录编号'),'owner':f('负责人'),'due_date':f('截止日期','date'),'status':f('整改状态','select',True,['open','in_progress','review','closed']),'remediation':f('整改证据','text',False),'review_result':f('复查结果','text',False),'reviewer':f('复查人','text',False)}),
 'target':dict(label='目标 / 预算 / 预测',fields={'start':f('开始日期','date'),'end':f('结束日期','date'),'channel':f('渠道（空为全渠道）','text',False),'scenario':f('口径','select',True,['budget','forecast']),'revenue':f('已履约收入目标','number',False),'cost':f('经营成本预算','number',False),'occupancy':f('入住率目标0至1','number',False),'owner':f('负责人')})
}
SCHEMAS.update(business.schemas(f))
SCHEMAS['fulfillment']['fields'].update({'product_code':f('产品代码','text',False),'entitlement_code':f('核销权益代码','text',False),'redeemed_units':f('核销份数','number',False)})
SCHEMAS['cost']['fields']['product_code']=f('分摊产品代码','text',False)
SCHEMAS['payment']['fields']['fulfillment_ref']=f('定向冲回的履约外部编号（空为按剩余权益分摊）','text',False)
SCHEMAS['issue']['fields']['alert_key']=f('来源预警/检查标识','text',False)
ROLES={'admin':set(SCHEMAS),'manager':{'inventory','order','reservation','fulfillment','customer','issue','coverage','target'},'finance':{'payment','cost','contract','operator_entry','coverage','target','issue'},'operations':{'campaign','customer','order','reservation','issue'}}
ROLES['manager'].update({'alert_rule','product','entitlement','sop_item','sop_check','review'})
ROLES['finance'].update({'alert_rule','entitlement'})
ROLES['operations'].update({'touchpoint','review','product'})
FINANCIAL={'payment','cost','contract','operator_entry','coverage'}

def connect():
 c=sqlite3.connect(DB,timeout=20);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
@contextmanager
def db():
 c=connect()
 try: yield c; c.commit()
 except: c.rollback();raise
 finally:c.close()
def password_hash(password,salt):return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def init_db():
 bootstrap=not DB.exists()
 with db() as c:
  c.execute('PRAGMA journal_mode=WAL')
  c.executescript('''CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,dataset TEXT NOT NULL,property_id TEXT NOT NULL,external_id TEXT NOT NULL,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL,UNIQUE(kind,dataset,property_id,external_id));
 CREATE INDEX IF NOT EXISTS records_scope ON records(dataset,kind,property_id);
 CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,hash TEXT NOT NULL,role TEXT NOT NULL,properties TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
 CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER, demo INTEGER NOT NULL DEFAULT 0,expires TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT,actor TEXT,action TEXT,record_id INTEGER,dataset TEXT,property_id TEXT,detail TEXT);
 CREATE TABLE IF NOT EXISTS imports(id INTEGER PRIMARY KEY,at TEXT,actor TEXT,kind TEXT,dataset TEXT,property_id TEXT,filename TEXT,inserted INTEGER,skipped INTEGER,status TEXT,detail TEXT);
 CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY,attempts INTEGER,until TEXT);
 ''')
  if not c.execute('SELECT 1 FROM users').fetchone():
   password=secrets.token_urlsafe(18);salt=secrets.token_hex(16)
   c.execute('INSERT INTO users(username,salt,hash,role,properties) VALUES(?,?,?,?,?)',('admin',salt,password_hash(password,salt),'admin','["*"]'))
   path=DATA/'admin-password.txt';path.write_text('username: admin\npassword: '+password+'\n',encoding='utf8');path.chmod(0o600)
  for dataset in (['actual','demo'] if bootstrap else []):
   for code,name,business,note in [
    ('bhl','森活百花里','hotel','中高端独栋、私汤；历史约60间或60余间，当前房量待确认'),('jtw','森活金汤湾','hotel','历史介绍62间；含温泉、餐饮、宴会及包厢，当前口径待确认'),('520','森活520','hotel','用户明确12间，逐日可售与开放状态待确认'),('bhcs','百花村舍','restaurant','餐饮拟独立运营，服务住客、外来客、宴请和团建'),('jtxy','金汤小院','restaurant','餐饮拟独立运营'),('water','森动水世界','water','季节经营，按实际营业日历统计'),('spa','B05 芳疗 SPA','spa','室外芳疗SPA试点'),('other','筹备及其他配套','other','高端餐饮、清吧、夜宵、电商、康养等筹备业务')]:
    payload=dict(code=code,name=name,business=business,status='unconfirmed',planned_rooms=None,physical_rooms=12 if code=='520' else None,note=note)
    c.execute('INSERT OR IGNORE INTO records(kind,dataset,property_id,external_id,payload,updated_at) VALUES(?,?,?,?,?,?)',('property',dataset,code,code,json.dumps(payload,ensure_ascii=False),NOW()))

def unpack(row):
 d=dict(row);d['data']=json.loads(d.pop('payload'));return d
def records(c,dataset,kind=None,props=None):
 q='SELECT * FROM records WHERE dataset=?';args=[dataset]
 if kind:q+=' AND kind=?';args.append(kind)
 if props is not None:
  if not props:return []
  q+=' AND property_id IN ('+','.join('?'*len(props))+')';args+=list(props)
 return [unpack(r) for r in c.execute(q+' ORDER BY id',args)]
def err(msg,status=422):raise HTTPException(status,msg)
def auth(request):
 token=request.cookies.get('hotel_session','')
 with db() as c:
  row=c.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),NOW())).fetchone()
  if not row:err('请先登录',401)
  if row['demo']:return dict(username='演示管理员',role='admin',properties=['*'],demo=True)
  u=c.execute('SELECT * FROM users WHERE id=? AND active=1',(row['user_id'],)).fetchone()
  if not u:err('账号已停用',401)
  return dict(username=u['username'],role=u['role'],properties=json.loads(u['properties']),demo=False)
def scope(user,dataset,prop=None,kind=None,write=False):
 if dataset not in ['actual','demo']:err('数据集只能是 actual 或 demo')
 if user['demo'] and dataset!='demo':err('演示会话不能访问真实数据',403)
 if prop and '*' not in user['properties'] and prop not in user['properties']:err('无此酒店或项目权限',403)
 if write and kind not in ROLES[user['role']]:err('当前角色无此管理权限',403)
 if user['role']=='operations' and kind in FINANCIAL:err('线上运营角色不能访问财务明细',403)
def allowed_props(c,user,dataset,prop):
 scope(user,dataset,prop)
 return [prop] if prop else (None if '*' in user['properties'] else user['properties'])
def audit(c,u,action,rid,dataset,prop,detail):
 c.execute('INSERT INTO audit(at,actor,action,record_id,dataset,property_id,detail) VALUES(?,?,?,?,?,?,?)',(NOW(),u['username'],action,rid,dataset,prop,json.dumps(detail,ensure_ascii=False)))
def dateval(value):
 try:
  if len(value)!=10 or date.fromisoformat(value).isoformat()!=value:raise ValueError()
  return value
 except:err('日期格式必须为有效 YYYY-MM-DD')
def validate(kind,data):
 if not isinstance(data,dict):err('记录内容必须为字段对象')
 if kind not in SCHEMAS:err('未知记录类型')
 if set(data)-set(SCHEMAS[kind]['fields']):err('存在未知字段，请使用当前模板或字段字典')
 out={}
 for key,s in SCHEMAS[kind]['fields'].items():
  v=data.get(key)
  if v is None or v=='':
   if s['required']:err(s['label']+'不能为空')
   out[key]=None if s['type'] in ['number','integer'] else '';continue
  typ=s['type']
  if typ in ['number','integer']:
   try:v=float(v)
   except:err(s['label']+'必须为数字')
   if not math.isfinite(v) or v<0:err(s['label']+'必须为非负有限数字')
   if typ=='integer' and not v.is_integer():err(s['label']+'必须为整数')
   v=int(v) if typ=='integer' else round(v,4 if key in ['rate','occupancy','threshold'] else 2)
  elif typ=='bool':
   if str(v).lower() not in ['true','false','1','0']:err(s['label']+'必须为 true 或 false')
   v=str(v).lower() in ['true','1']
  else:
   v=str(v).strip()
   if s['required'] and not v:err(s['label']+'不能为空白')
   if len(v)>2000:err(s['label']+'过长')
   if key in ['content','response','evidence','remediation','note','reason','review_result']:
    v=re.sub(r'(?<![0-9])(1[3-9][0-9])([0-9]{4})([0-9]{4})(?![0-9])',r'\1****\3',v)
    v=re.sub(r'([A-Za-z0-9])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})',r'\1***\2',v)
   if typ=='date':dateval(v)
   if typ=='select' and v not in s['options']:err(s['label']+'选项无效')
  out[key]=v
 if kind=='property' and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',out['code']):err('项目代码仅允许1至64位英文字母、数字、下划线和连字符')
 if kind=='property' and out['physical_rooms'] is not None and out['planned_rooms'] is not None and out['physical_rooms']>out['planned_rooms']:err('物理房量不能大于规划房量')
 if kind=='inventory':
  if out['available']+out['out_of_service']>out['physical']:err('可售加停用不能超过物理房量')
  if out['locked']>out['available']:err('锁房不能超过可售')
  if not out['is_open'] and out['available']>0:err('未营业日期可售数必须为0')
 if kind in ['contract','target']:
  if out['start']>out['end']:err('开始日期不能晚于结束日期')
  for key in ['rate','occupancy']:
   if out.get(key) is not None and out[key]>1:err('比例必须在0至1之间')
 if kind=='order' and (out['checkin']>out['checkout'] or (out['kind']=='stay' and out['checkin']==out['checkout'])):err('服务日期无效；住宿离店日须晚于入住日')
 if kind=='order':
  principal=out.get('principal_amount') or 0
  if principal>out['booking_amount'] or (out['kind']!='consignment' and principal):err('货主本金仅适用于代销且不能超过交易额')
  if out['kind']=='consignment' and out.get('principal_amount') is None:err('代销订单必须明确货主本金，净额确认服务收入')
 if kind=='fulfillment':
  if out['included'] and out['amount']!=0:err('含于房费的赠送权益收入必须为0，避免重复确认')
  if out['business']!='room' and out['room_nights']!=0:err('非客房权益不能增加间夜')
  if out['business']=='room' and out['room_nights']==0:err('客房履约必须记录实际间夜')
 if kind=='payment':
  if out['type']!='refund' and out['revenue_reversal']!=0:err('只有退款可冲减已履约收入')
  if out['revenue_reversal']>out['amount']:err('收入冲减不能大于退款额')
  if out['type']=='platform_fee' and out['destination']!='platform':err('平台结算扣款必须记录在平台账户')
  if out['type'] in ['settlement','principal_payout'] and out['destination']!='bank':err('结算到账及代销本金付款必须使用银行账户')
  if out['type']!='refund' and (out.get('principal_reversal') or 0):err('只有退款可冲减货主本金')
  if out['revenue_reversal']+(out.get('principal_reversal') or 0)>out['amount']:err('收入冲减与本金冲减合计不能超过退款额')
 if kind=='customer' and out['phone_last4'] and (len(out['phone_last4'])!=4 or not out['phone_last4'].isdigit()):err('客户信息仅允许手机号末4位')
 if kind=='issue' and out['status']=='closed' and not all(out[k] for k in ['remediation','review_result','reviewer']):err('关闭必须有整改证据、复查结果及复查人')
 if kind=='operator_entry' and out['type']=='commission_received' and not out['contract_code']:err('佣金到账必须关联实际合同')
 try:business.validate(kind,out)
 except ValueError as ex:err(str(ex))
 return out

def check_relations(c,dataset):
 rs=records(c,dataset);index={}
 for r in rs:index.setdefault((r['property_id'],r['kind']),[]).append({**r['data'],'_id':r['id'],'_external':r['external_id'],'_property':r['property_id']})
 for (prop,kind),items in index.items():
  if kind=='property':continue
  if not index.get((prop,'property')):err('酒店/项目不存在')
  orders={x['order_no']:x for x in index.get((prop,'order'),[])};contracts={x['code']:x for x in index.get((prop,'contract'),[])}
  natural={'order':lambda x:x['order_no'],'contract':lambda x:x['code'],'campaign':lambda x:x['code'],'customer':lambda x:x['code'],'inventory':lambda x:(x['day'],x['room_type']),'coverage':lambda x:x['day'],'reservation':lambda x:(x['order_no'],x['day'],x['room_type'])}
  if kind in natural:
   keys=[natural[kind](x) for x in items]
   if len(keys)!=len(set(keys)):err(f'{SCHEMAS[kind]["label"]}的业务键重复')
  for x in items:
   if x.get('order_no') and kind!='order' and x['order_no'] not in orders:err('关联订单不存在：'+x['order_no'])
   if x.get('contract_code') and x['contract_code'] not in contracts:err('关联合同不存在')
   if kind=='order':
    if x.get('campaign_code') and x['campaign_code'] not in {a['code'] for a in index.get((prop,'campaign'),[])}:err('营销活动不存在')
    if x.get('contract_code') and not contracts[x['contract_code']]['start']<=x['order_date']<=contracts[x['contract_code']]['end']:err('订单日期不在合同有效期内')
   if kind in ['fulfillment','reservation']:
    o=orders[x['order_no']]
    if kind=='fulfillment' and o['kind']=='consignment' and x['business']!='consignment_fee':err('代销仅确认 consignment_fee 净服务收入，不将商品本金计入收入')
    if kind=='fulfillment' and o['status']=='cancelled':err('已取消订单不能保留履约记录；请先核对收入冲回和订单状态')
    if o['kind']=='stay' and not o['checkin']<=x['day']<o['checkout']:err('住宿间夜必须在入住至离店前一日范围内')
    if kind=='reservation' and x['status']=='confirmed' and o['status']=='cancelled':err('已取消订单不能保留确认预约')
  if kind=='order':
   for no,o in orders.items():
    fs=[a for a in index.get((prop,'fulfillment'),[]) if a['order_no']==no];ps=[a for a in index.get((prop,'payment'),[]) if a['order_no']==no]
    fulfilled=sum(a['amount'] for a in fs);paid=sum(a['amount'] for a in ps if a['type']=='collection');refund=sum(a['amount'] for a in ps if a['type']=='refund');reversal=sum(a['revenue_reversal'] for a in ps)
    if fulfilled>o['booking_amount']-(o.get('principal_amount') or 0)+.01:err('套餐分摊/累计履约超过订单交易额：'+no)
    principal=o.get('principal_amount') or 0
    principal_reversed=sum(a.get('principal_reversal') or 0 for a in ps)
    principal_paid=sum(a['amount'] for a in ps if a['type']=='principal_payout')
    if (principal_reversed or principal_paid) and o['kind']!='consignment':err('非代销订单不能包含货主本金变动')
    if principal_reversed>principal+.01 or principal_paid>min(max(paid-refund,0),principal-principal_reversed)+.01:err('货主本金冲减或付款超过可用本金')
    if paid>o['booking_amount']+.01 or refund>paid+.01:err('累计收款不能超过交易额，退款不能超过收款：'+no)
    if reversal>fulfilled+.01 or fulfilled-reversal>paid-refund+.01 and o['status']=='cancelled':err('收入冲减与履约记录不一致：'+no)
    platform=sum(a['amount']*(1 if a['type']=='collection' else -1) for a in ps if a['destination']=='platform' and a['type']!='settlement')
    settlements=sum(a['amount'] for a in ps if a['type']=='settlement')
    if settlements>platform+.01:err('平台结算金额超过平台净收款：'+no)
    for p in ps:
     if p['type']=='refund':
      if sum(a['amount'] for a in ps if a['type']=='refund' and a['day']<=p['day'])>sum(a['amount'] for a in ps if a['type']=='collection' and a['day']<=p['day'])+.01:err('退款日期早于可用收款')
      if sum(a['revenue_reversal'] for a in ps if a['day']<=p['day'])>sum(a['amount'] for a in fs if a['day']<=p['day'])+.01:err('收入冲减日期早于对应履约')

 try:business.validate_relations(index)
 except ValueError as ex:err(str(ex))

def save_record(c,u,kind,dataset,prop,ext,data,rid=None,version=None):
 scope(u,dataset,prop,kind,True)
 if not isinstance(ext,str) or not ext.strip() or len(ext)>100:err('external_id 必须是非空字符串且最多100字')
 if not isinstance(prop,str) or not prop:err('必须指定有效项目代码')
 ext=ext.strip()
 clean=validate(kind,data)
 if kind=='property' and clean['code']!=prop:err('项目代码必须与项目范围一致')
 if rid:
  old=c.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone()
  if not old:err('记录不存在',404)
  if (old['kind'],old['dataset'],old['property_id'])!=(kind,dataset,prop):err('不可更换记录类型、数据集或项目')
  if version!=old['version']:err('记录已更新，请刷新后重试',409)
  previous=json.loads(old['payload'])
  if kind=='issue' and previous.get('alert_key') and previous['alert_key']!=clean.get('alert_key'):err('已绑定的预警或检查来源不可修改')
  if kind=='issue' and previous.get('alert_key','').startswith('SOP:') and previous['severity']=='redline' and clean['severity']!='redline':err('SOP产生的红线不能降级，应完成整改复查后关闭')
  changed=c.execute('UPDATE records SET external_id=?,payload=?,version=version+1,updated_at=? WHERE id=? AND version=?',(ext,json.dumps(clean,ensure_ascii=False),NOW(),rid,version))
  if changed.rowcount!=1:err('记录已被并发更新，请刷新后重试',409)
  audit(c,u,'update',rid,dataset,prop,{'before':json.loads(old['payload']),'after':clean})
 else:
  try:rid=c.execute('INSERT INTO records(kind,dataset,property_id,external_id,payload,updated_at) VALUES(?,?,?,?,?,?)',(kind,dataset,prop,ext,json.dumps(clean,ensure_ascii=False),NOW())).lastrowid
  except sqlite3.IntegrityError:err('外部编号重复；请编辑原记录，不能覆盖导入',409)
  audit(c,u,'create',rid,dataset,prop,{'after':clean})
 if kind=='sop_check' and clean['result']=='fail':
  item=next((r['data'] for r in records(c,dataset,'sop_item',[prop]) if r['data']['code']==clean['item_code']),None)
  if item:
   key='SOP:'+ext
   prior=[r for r in records(c,dataset,'issue',[prop]) if r['data'].get('alert_key')==key and r['data']['status']!='closed']
   if not prior:
    save_record(c,u,'issue',dataset,prop,'SOP-'+str(rid)+'-'+secrets.token_hex(3),{'day':clean['day'],'department':item['department'],'title':'SOP不合格：'+item['title'],'severity':'redline' if item['redline'] else 'major','order_no':'','evidence':clean['evidence'],'owner':clean['owner'],'due_date':clean['due_date'],'status':'open','alert_key':key})
 return rid

async def read_json(request):
 content=bytearray()
 async for chunk in request.stream():
  content.extend(chunk)
  if len(content)>8*1024*1024:err('请求数据超过8MB',413)
 try:data=json.loads(content)
 except (ValueError,UnicodeDecodeError):err('请求必须是有效JSON',400)
 if not isinstance(data,dict):err('JSON请求必须是对象',400)
 return data

app=FastAPI(title='森活森动 CEO 经营驾驶舱')
@app.middleware('http')
async def protect(request,call_next):
 if request.method not in ['GET','HEAD','OPTIONS']:
  origin=request.headers.get('origin')
  if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
   return JSONResponse({'detail':'不允许跨来源修改'},status_code=403)
  if request.headers.get('sec-fetch-site')=='cross-site':return JSONResponse({'detail':'不允许跨站修改'},status_code=403)
 response=await call_next(request)
 response.headers['X-Content-Type-Options']='nosniff';response.headers['X-Frame-Options']='DENY';response.headers['Referrer-Policy']='same-origin';response.headers['Cache-Control']='no-store'
 return response
@app.exception_handler(sqlite3.IntegrityError)
async def conflict(request,exc):return JSONResponse({'detail':'记录编号已存在或关联约束不满足'},status_code=409)
@app.exception_handler(sqlite3.OperationalError)
async def unavailable(request,exc):return JSONResponse({'detail':'数据库暂时忙碌或不可用，请稍后重试'},status_code=503)
@app.get('/')
def home():return FileResponse(ROOT/'index.html')
@app.get('/app.js')
def javascript():return FileResponse(ROOT/'app.js',media_type='text/javascript')
@app.get('/style.css')
def stylesheet():return FileResponse(ROOT/'style.css',media_type='text/css')
@app.get('/api/health')
def health():
 with db() as c:c.execute('SELECT 1')
 return {'status':'ok','database':'sqlite','today':TODAY()}
@app.post('/api/login')
async def login(request:Request):
 body=await read_json(request);demo=body.get('demo') is True
 if demo and os.environ.get('HOTEL_ALLOW_DEMO','1')!='1':err('此部署已关闭公开演示登录',403)
 with db() as c:
  uid=None
  if not demo:
   username=str(body.get('username',''));key=(request.client.host if request.client else '')+':'+username
   attempt=c.execute('SELECT * FROM login_attempts WHERE key=?',(key,)).fetchone()
   if attempt and attempt['until']>NOW() and attempt['attempts']>=8:err('尝试过多，请15分钟后再试',429)
   u=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
   if not u or not hmac.compare_digest(password_hash(str(body.get('password','')),u['salt']),u['hash']):
    attempts=(attempt['attempts'] if attempt and attempt['until']>NOW() else 0)+1
    c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)',(key,attempts,(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()));c.commit();err('账号或密码错误',401)
   uid=u['id'];c.execute('DELETE FROM login_attempts WHERE key=?',(key,))
  token=secrets.token_urlsafe(32)
  c.execute('DELETE FROM sessions WHERE expires<?',(NOW(),))
  c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,int(demo),(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()))
 response=JSONResponse({'ok':True});response.set_cookie('hotel_session',token,httponly=True,samesite='strict',secure=os.environ.get('HOTEL_SECURE_COOKIE')=='1',max_age=28800);return response
@app.post('/api/logout')
def logout(request:Request):
 with db() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get('hotel_session','').encode()).hexdigest(),))
 r=JSONResponse({'ok':True});r.delete_cookie('hotel_session');return r
@app.get('/api/me')
def me(request:Request):return auth(request)
@app.get('/api/schema')
def schema(request:Request):
 u=auth(request);return {'schemas':{k:v for k,v in SCHEMAS.items() if not(u['role']=='operations' and k in FINANCIAL)},'writable':list(ROLES[u['role']]),'today':TODAY()}
@app.get('/api/records/{kind}')
def listing(kind:str,request:Request,dataset:str='actual',property_id:str=''):
 u=auth(request);scope(u,dataset,property_id,kind)
 with db() as c:
  rs=records(c,dataset,kind,allowed_props(c,u,dataset,property_id))
 return {'records':rs}

@app.get('/api/export/{kind}')
def export_records(kind:str,request:Request,dataset:str='actual',property_id:str='',start:str='',end:str=''):
 u=auth(request);scope(u,dataset,property_id,kind)
 if kind not in SCHEMAS:err('未知记录类型')
 with db() as c:rs=records(c,dataset,kind,allowed_props(c,u,dataset,property_id))
 if start or end:
  day_range(start,end)
  rs=[r for r in rs if not(r['data'].get('day') or r['data'].get('order_date')) or start<=(r['data'].get('day') or r['data'].get('order_date'))<=end]
 out=io.StringIO();writer=csv.writer(out);keys=list(SCHEMAS[kind]['fields']);writer.writerow(['property_id','external_id',*keys,'version','updated_at'])
 def safe(v):
  if v is None:return ''
  if isinstance(v,bool):return 'true' if v else 'false'
  text=str(v)
  return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
 for r in rs:writer.writerow([safe(r['property_id']),safe(r['external_id']),*[safe(r['data'].get(k)) for k in keys],r['version'],r['updated_at']])
 return Response(('\ufeff'+out.getvalue()).encode(),media_type='text/csv;charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{dataset}-{kind}.csv"'})

@app.post('/api/records/{kind}')
async def create(kind:str,request:Request):
 u=auth(request);b=await read_json(request)
 with db() as c:
  rid=save_record(c,u,kind,b.get('dataset','actual'),b.get('property_id',''),b.get('external_id',''),b.get('data',{}));check_relations(c,b.get('dataset','actual'))
 return {'id':rid}
@app.put('/api/records/{kind}/{rid}')
async def update(kind:str,rid:int,request:Request):
 u=auth(request);b=await read_json(request)
 with db() as c:
  save_record(c,u,kind,b.get('dataset','actual'),b.get('property_id',''),b.get('external_id',''),b.get('data',{}),rid,b.get('version'));check_relations(c,b.get('dataset','actual'))
 return {'id':rid}
@app.delete('/api/records/{kind}/{rid}')
def delete(kind:str,rid:int,request:Request,version:int):
 u=auth(request)
 with db() as c:
  row=c.execute('SELECT * FROM records WHERE id=? AND kind=?',(rid,kind)).fetchone()
  if not row:err('记录不存在',404)
  scope(u,row['dataset'],row['property_id'],kind,True)
  if row['version']!=version:err('记录版本已变化',409)
  original=json.loads(row['payload'])
  if kind=='issue' and original['severity']=='redline' and original['status']!='closed':err('未关闭红线不能删除，请完成整改与复查',409)
  changed=c.execute('DELETE FROM records WHERE id=? AND version=?',(rid,version))
  if changed.rowcount!=1:err('记录已被并发更新，请刷新',409)
  check_relations(c,row['dataset']);audit(c,u,'delete',rid,row['dataset'],row['property_id'],{'before':original})
 return {'ok':True}

def import_rows(c,u,kind,dataset,prop,rows):
 scope(u,dataset,prop,kind,True)
 if len(rows)>5000:err('每批最多5000条')
 inserted=skipped=0
 for i,row in enumerate(rows):
  if not isinstance(row,dict):err('导入的每行必须为字段对象')
  ext=str(row.get('external_id','')).strip();data={k:row.get(k) for k in SCHEMAS[kind]['fields']}
  try:
   clean=validate(kind,data)
   old=c.execute('SELECT * FROM records WHERE kind=? AND dataset=? AND property_id=? AND external_id=?',(kind,dataset,prop,ext)).fetchone()
   if old:
    if validate(kind,json.loads(old['payload']))==clean:skipped+=1;continue
    err('同一外部编号的数据已变化，请通过编辑操作更新，不能静默覆盖',409)
   save_record(c,u,kind,dataset,prop,ext,clean);inserted+=1
  except HTTPException as ex:err(f'第{i+2}行：{ex.detail}',ex.status_code)
 check_relations(c,dataset)
 return {'inserted':inserted,'skipped':skipped}
@app.get('/api/template/{kind}')
def template(kind:str,request:Request,format:str='csv'):
 u=auth(request)
 if kind not in SCHEMAS:err('未知数据类型')
 header=['external_id',*SCHEMAS[kind]['fields']]
 if format=='xlsx':
  wb=Workbook();ws=wb.active;ws.title='数据';ws.append(header);out=io.BytesIO();wb.save(out);content=out.getvalue();mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
 else:
  content=('\ufeff'+','.join(header)+'\n').encode();format='csv';mime='text/csv;charset=utf-8'
 return Response(content,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{kind}-template.{format}"'})
@app.post('/api/import/preview')
async def preview(request:Request,kind:str,dataset:str,property_id:str,filename:str):
 u=auth(request);scope(u,dataset,property_id,kind,True)
 if kind not in SCHEMAS:err('未知数据类型')
 content=bytearray()
 async for part in request.stream():
  content.extend(part)
  if len(content)>3*1024*1024:err('文件最多3MB')
 try:
  if filename.lower().endswith('.xlsx'):
   import zipfile
   z=zipfile.ZipFile(io.BytesIO(content))
   if sum(x.file_size for x in z.infolist())>30*1024*1024:err('Excel解压后超过30MB')
   wb=load_workbook(io.BytesIO(content),read_only=True,data_only=False);ws=wb.active
   cells=[]
   for row in ws.iter_rows(values_only=True):
    cells.append([x.isoformat()[:10] if isinstance(x,(datetime,date)) else x for x in row])
    if len(cells)>5001:err('每批最多5000条')
   wb.close()
   if not cells:err('文件为空')
   headers=cells[0];rows=[dict(zip(headers,r)) for r in cells[1:] if any(v is not None for v in r)]
  elif filename.lower().endswith('.csv'):
   reader=csv.DictReader(io.StringIO(bytes(content).decode('utf-8-sig')));headers=reader.fieldnames;rows=list(reader)
  else:err('仅支持 UTF-8 CSV 和 .xlsx')
  expected=['external_id',*SCHEMAS[kind]['fields']]
  if headers!=expected:err('表头或顺序不匹配，请下载本类型模板')
  if not rows:err('没有可导入的数据行')
  with db() as c:
   c.execute('SAVEPOINT preview')
   try:result=import_rows(c,u,kind,dataset,property_id,rows)
   finally:c.execute('ROLLBACK TO preview');c.execute('RELEASE preview')
  return {**result,'rows':rows,'filename':filename,'kind':kind,'dataset':dataset,'property_id':property_id}
 except HTTPException:raise
 except Exception:err('无法读取文件，请检查编码、格式与数据；不接受公式单元格')
@app.post('/api/import/commit')
async def import_commit(request:Request):
 u=auth(request);b=await read_json(request);kind=b.get('kind');dataset=b.get('dataset');prop=b.get('property_id');scope(u,dataset,prop,kind,True)
 if kind not in SCHEMAS or not isinstance(b.get('rows'),list):err('导入内容无效')
 try:
  with db() as c:
   result=import_rows(c,u,kind,dataset,prop,b['rows'])
   c.execute('INSERT INTO imports(at,actor,kind,dataset,property_id,filename,inserted,skipped,status,detail) VALUES(?,?,?,?,?,?,?,?,?,?)',(NOW(),u['username'],kind,dataset,prop,str(b.get('filename','手工批次'))[:200],result['inserted'],result['skipped'],'success','原子提交'))
  return result
 except HTTPException as ex:
  with db() as c:c.execute('INSERT INTO imports(at,actor,kind,dataset,property_id,filename,inserted,skipped,status,detail) VALUES(?,?,?,?,?,?,?,?,?,?)',(NOW(),u['username'],kind,dataset,prop,str(b.get('filename',''))[:200],0,0,'failed',str(ex.detail)))
  raise
@app.get('/api/logs')
def logs(request:Request,dataset:str='actual',property_id:str=''):
 u=auth(request);scope(u,dataset,property_id)
 with db() as c:
  props=allowed_props(c,u,dataset,property_id)
  def read(table):
   q=f'SELECT * FROM {table} WHERE dataset=?';args=[dataset]
   if props is not None:q+=' AND property_id IN ('+','.join('?'*len(props))+')';args+=props
   if u['role']!='admin':q+=' AND actor=?';args.append(u['username'])
   return [dict(x) for x in c.execute(q+' ORDER BY id DESC LIMIT 100',args)]
  return {'imports':read('imports'),'audit':read('audit')}
@app.get('/api/users')
def users(request:Request):
 u=auth(request)
 if u['role']!='admin' or u['demo']:err('仅真实集团管理员可管理账号',403)
 with db() as c:return {'users':[dict(r) for r in c.execute('SELECT id,username,role,properties,active FROM users')]}
@app.post('/api/users')
async def create_user(request:Request):
 u=auth(request)
 if u['role']!='admin' or u['demo']:err('仅真实集团管理员可管理账号',403)
 b=await read_json(request);role=b.get('role');props=b.get('properties',[]);username=str(b.get('username','')).strip();password=str(b.get('password',''))
 if not isinstance(role,str) or role not in ROLES or not username or len(username)>60 or len(password)<12 or len(password)>200 or not isinstance(props,list) or not props:err('需要有效角色、用户名、至少12位密码及酒店范围')
 if role!='admin' and '*' in props:err('非集团管理员必须指定具体项目')
 with db() as c:
  known={r['property_id'] for r in records(c,'actual','property')}
  if any(p!='*' and p not in known for p in props):err('存在未知项目范围')
  salt=secrets.token_hex(16);c.execute('INSERT INTO users(username,salt,hash,role,properties) VALUES(?,?,?,?,?)',(username,salt,password_hash(password,salt),role,json.dumps(props)))
  audit(c,u,'user_create',None,'actual','',{'username':username,'role':role,'properties':props})
 return {'ok':True}
@app.post('/api/users/{uid}/disable')
def disable_user(uid:int,request:Request):
 u=auth(request)
 if u['role']!='admin' or u['demo']:err('仅真实集团管理员可停用账号',403)
 with db() as c:
  row=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
  if not row:err('账号不存在',404)
  if row['username']==u['username']:err('不能停用当前账号')
  c.execute('UPDATE users SET active=0 WHERE id=?',(uid,));c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));audit(c,u,'user_disable',None,'actual','',{'username':row['username']})
 return {'ok':True}

def day_range(start,end):
 a=date.fromisoformat(dateval(start));b=date.fromisoformat(dateval(end))
 if b<a or (b-a).days>365:err('选择有效日期范围（最多366天）')
 return [(a+timedelta(days=i)).isoformat() for i in range((b-a).days+1)]
def metrics(rs,start,end,asof):
 days=day_range(start,end);within=lambda d:start<=d<=end
 group={k:[{**r['data'],'_id':r['id'],'_property':r['property_id'],'_external':r['external_id']} for r in rs if r['kind']==k] for k in SCHEMAS}
 orders={(o['_property'],o['order_no']):o for o in group['order']}
 fs=[x for x in group['fulfillment'] if within(x['day'])];ps=[x for x in group['payment'] if within(x['day'])]
 pastpay=[x for x in group['payment'] if x['day']<=end];pastfs=[x for x in group['fulfillment'] if x['day']<=end]
 costs=[x for x in group['cost'] if within(x['day']) and x['scope']=='park'];campaigns=[x for x in group['campaign'] if within(x['day'])]
 total=lambda xs,key='amount':round(sum(x.get(key) or 0 for x in xs),2)
 gross=total(fs);reversal=total(ps,'revenue_reversal');revenue=round(gross-reversal,2)
 allocations=[]
 for key in orders:
  allocations+=business.reversal_allocations([x for x in pastfs if (x['_property'],x['order_no'])==key],[x for x in pastpay if (x['_property'],x['order_no'])==key])
 room_gross=total([x for x in fs if x['business']=='room']);room_reversal=total([x for x in allocations if within(x['day']) and x['business']=='room'])
 room_revenue=round(room_gross-room_reversal,2);nights=total(fs,'room_nights')
 inventory=[x for x in group['inventory'] if within(x['day'])]
 hotel_codes={p['code'] for p in group['property'] if p['business']=='hotel'}
 available=total([x for x in inventory if x['_property'] in hotel_codes],'available');inv_keys={(x['_property'],x['day'],x['room_type']) for x in inventory}
 recorded_props={x['_property'] for x in group['inventory']+group['fulfillment']+group['reservation']}
 hotel_props=[x for x in group['property'] if x['business']=='hotel' and (x['status'] not in ['closed','planning'] or x['code'] in recorded_props)]
 known_types={p['code']:{x['room_type'] for x in group['inventory'] if x['_property']==p['code']} or {'unknown'} for p in hotel_props}
 expected={(p['code'],d,t) for p in hotel_props for d in days for t in known_types[p['code']]};inventory_complete=bool(expected) and expected<=inv_keys
 # A missing inventory row never becomes a zero-night denominator.
 availability=available if inventory_complete else None
 active_props=[p for p in group['property'] if p['status'] not in ['closed','planning'] or p['code'] in {x['_property'] for x in fs+costs+inventory}]
 closed={(x['_property'],x['day']) for x in inventory if not any(y['is_open'] for y in inventory if (x['_property'],x['day'])==(y['_property'],y['day']))}
 coverage_expected={(p['code'],d) for p in active_props for d in days} - closed
 coverage={(x['_property'],x['day']) for x in group['coverage'] if x['complete']}
 missing_cost=len(coverage_expected-coverage)
 cost_complete=bool(coverage_expected) and not missing_cost and all(x['amount'] is not None for x in costs) and all(x['spend'] is not None for x in campaigns)
 contracts={(x['_property'],x['code']):x for x in group['contract']}
 commissions=[]
 for key,o in orders.items():
  contract=contracts.get((key[0],o['contract_code']))
  if not contract:continue
  ofs=[x for x in fs if (x['_property'],x['order_no'])==key];ops=[x for x in ps if (x['_property'],x['order_no'])==key]
  basis=total(ofs)-total(ops,'revenue_reversal') if contract['basis']=='fulfilled' else total([x for x in ops if x['type']=='collection'])-total([x for x in ops if x['type']=='refund'])
  commissions.append({'order_no':key[1],'property_id':key[0],'contract_code':contract['code'],'amount':round(basis*contract['rate'],2),'beneficiary':contract['beneficiary']})
 commission=total(commissions);spend=total(campaigns,'spend');known_cost=total(costs);contribution=round(revenue-known_cost-spend-commission,2)
 collections=total([x for x in ps if x['type']=='collection']);refunds=total([x for x in ps if x['type']=='refund'])
 receipts=total([x for x in ps if x['destination']=='bank' and x['type'] in ['collection','settlement']])-total([x for x in ps if x['destination']=='bank' and x['type']=='refund'])
 pending=advance=receivable=principal_liability=0;late=[];details=[]
 for key,o in orders.items():
  op=[x for x in pastpay if (x['_property'],x['order_no'])==key];of=[x for x in pastfs if (x['_property'],x['order_no'])==key]
  paid=total([x for x in op if x['type']=='collection'])-total([x for x in op if x['type']=='refund']);fulfilled=total(of)-total(op,'revenue_reversal')
  wait=total([x for x in op if x['destination']=='platform' and x['type']=='collection'])-total([x for x in op if x['destination']=='platform' and x['type']=='refund'])-total([x for x in op if x['type']=='settlement'])-total([x for x in op if x['type']=='platform_fee'])
  principal=max((o.get('principal_amount') or 0)-total(op,'principal_reversal'),0)
  principal_liability+=max(min(max(paid,0),principal)-total([x for x in op if x['type']=='principal_payout']),0)
  pending+=wait;advance+=max(paid-fulfilled-principal,0);receivable+=max(fulfilled-max(paid-principal,0),0)
  overdue=max(total([x for x in op if x['type']=='collection' and x['destination']=='platform' and x['due_date'] and x['due_date']<end])-total([x for x in op if x['type']=='settlement' or (x['destination']=='platform' and x['type'] in ['refund','platform_fee'])]),0)
  if wait>.01 and overdue>.01:late.append({'order_no':key[1],'property_id':key[0],'amount':round(min(wait,overdue),2),'owner':o['owner']})
  period_fs=[x for x in fs if (x['_property'],x['order_no'])==key];period_ps=[x for x in ps if (x['_property'],x['order_no'])==key]
  if period_fs or period_ps or within(o['order_date']):
   details.append({'id':o['_id'],'property_id':key[0],'order_no':key[1],'channel':o['channel'],'status':o['status'],'booking_amount':o['booking_amount'],'fulfilled_revenue':round(total(period_fs)-total(period_ps,'revenue_reversal'),2),'room_nights':total(period_fs,'room_nights'),'paid_net':round(total([x for x in period_ps if x['type']=='collection'])-total([x for x in period_ps if x['type']=='refund']),2),'pending':round(wait,2),'customer_code':o['customer_code'],'owner':o['owner']})
 future=[]
 for i in range(90):
  d=(date.fromisoformat(asof)+timedelta(days=i)).isoformat();iv=[x for x in group['inventory'] if x['day']==d];reserv=[x for x in group['reservation'] if x['day']==d]
  booked=sum(x['rooms'] for x in reserv if x['status']=='confirmed');can=total(iv,'available');locked=total(iv,'locked')
  keys={(x['_property'],x['room_type']) for x in iv};complete=bool(hotel_props) and {(p['code'],t) for p in hotel_props for t in known_types[p['code']]}<=keys
  future.append({'day':d,'available':can if complete else None,'booked':booked,'cancelled':sum(x['rooms'] for x in reserv if x['status']=='cancelled'),'locked':locked,'out_of_service':total(iv,'out_of_service'),'voucher_commitment':total(iv,'voucher_commitment'),'remaining':can-locked-booked if complete else None,'day_type':', '.join(sorted({x['day_type'] for x in iv})),'coverage':len(iv)})
 future_summary={}
 for n in [7,30,90]:
  xs=future[:n];den=sum(x['available'] or 0 for x in xs);complete=all(x['available'] is not None for x in xs)
  future_summary[str(n)]={'booked':sum(x['booked'] for x in xs),'available':den if complete else None,'pace':sum(x['booked'] for x in xs)/den if complete and den else None,'missing_days':sum(x['available'] is None for x in xs)}
 channels=[]
 for ch in sorted({x['channel'] for x in group['order']}|{x['channel'] for x in campaigns}):
  keys={k for k,o in orders.items() if o['channel']==ch};cf=[x for x in fs if (x['_property'],x['order_no']) in keys];cp=[x for x in ps if (x['_property'],x['order_no']) in keys];cc=[x for x in costs if (x['_property'],x['order_no']) in keys];ca=[x for x in campaigns if x['channel']==ch]
  cr=total(cf)-total(cp,'revenue_reversal');cs=total(ca,'spend');cm=total([x for x in commissions if (x['property_id'],x['order_no']) in keys])
  channels.append({'channel':ch,'fulfilled_revenue':round(cr,2),'spend':cs if all(x['spend'] is not None for x in ca) else None,'commission':cm,'linked_cost':total(cc),'known_contribution':round(cr-cs-cm-total(cc),2),'paid_orders':len({(x['_property'],x['order_no']) for x in cp if x['type']=='collection'}),'reserved_orders':len({(x['_property'],x['order_no']) for x in group['reservation'] if within(x['day']) and (x['_property'],x['order_no']) in keys and x['status']=='confirmed'}),'fulfilled_orders':len({(x['_property'],x['order_no']) for x in cf}),'refunds':total([x for x in cp if x['type']=='refund']),'impressions':sum(x['impressions'] or 0 for x in ca) if ca and all(x['impressions'] is not None for x in ca) else None,'consultations':sum(x['consultations'] or 0 for x in ca) if ca and all(x['consultations'] is not None for x in ca) else None})
 daily=[{'day':d,'revenue':round(total([x for x in fs if x['day']==d])-total([x for x in ps if x['day']==d],'revenue_reversal'),2) if any(x['day']==d for x in fs+ps) else None,'room_nights':total([x for x in fs if x['day']==d],'room_nights') if any(x['day']==d for x in fs) else None} for d in days]
 breakdown=[{'business':b,'fulfilled_gross':total([x for x in fs if x['business']==b]),'guests':total([x for x in fs if x['business']==b],'guests')} for b in ['room','dining','water','spa','goods','consignment_fee','membership','other']]
 issues=[x for x in group['issue'] if x['status']!='closed'];alerts=[]
 if not inventory_complete:alerts.append(dict(title='逐日可售房量未齐，入住率与RevPAR暂停计算',severity='major',evidence=f'缺失 {len({(p,d) for p,d,t in expected-inv_keys})} 个酒店日房态记录',department='data',property_id='',owner='',due_date=asof,order_no=''))
 if not cost_complete:alerts.append(dict(title='成本口径不完整，不能认定经营贡献或净利润',severity='major',evidence=f'缺少 {missing_cost} 个项目日完整性确认；另检查未知费用',department='finance',property_id='',owner='',due_date=asof,order_no=''))
 for x in late:alerts.append(dict(title='订单结算逾期',severity='major',evidence=f"{x['order_no']} 待结算 {x['amount']:.2f} 元",department='finance',property_id=x['property_id'],owner=x['owner'],due_date=asof,order_no=x['order_no']))
 for n in [7,30]:
  v=future_summary[str(n)]
  if v['pace'] is not None and v['pace']<.3:alerts.append(dict(title=f'未来{n}天预订不足（初始规则30%）',severity='normal',evidence=f"已确认{v['booked']}间夜 / 可售{v['available']}间夜；需结合淡旺季校准",department='marketing',property_id='',owner='',due_date=asof,order_no=''))
 if collections and refunds/collections>.2:alerts.append(dict(title='期间退款/收款超过20%（非同批订单退款率）',severity='major',evidence=f'期间退款{refunds} / 收款{collections}，需下钻核对订单批次',department='finance',property_id='',owner='',due_date=asof,order_no=''))
 for x in future:
  if x['remaining'] is not None and x['remaining']<0:alerts.append(dict(title='未来房态超卖或锁房冲突',severity='redline',evidence=f"{x['day']} 剩余可订 {x['remaining']} 间",department='rooms',property_id='',owner='',due_date=x['day'],order_no=''))
 targets=[x for x in group['target'] if x['start']==start and x['end']==end]
 budget=[x for x in targets if x['scenario']=='budget' and not x['channel']];budget_cost=total(budget,'cost') if budget and all(x['cost'] is not None for x in budget) else None
 if budget_cost is not None and known_cost+spend+commission>budget_cost:alerts.append(dict(title='已录入费用超过匹配期间预算',severity='major',evidence=f'已知费用{known_cost+spend+commission:.2f} / 预算{budget_cost:.2f}',department='finance',property_id='',owner='',due_date=asof,order_no=''))
 for key,o in orders.items():
  if o['status']!='completed' or o['checkout']>end:continue
  lifetime_fs=[x for x in pastfs if (x['_property'],x['order_no'])==key]
  lifetime_ps=[x for x in pastpay if (x['_property'],x['order_no'])==key]
  expected_revenue=o['booking_amount']-(o.get('principal_amount') or 0)-total([x for x in lifetime_ps if x['type']=='refund'])+total(lifetime_ps,'principal_reversal')
  if total(lifetime_fs)-total(lifetime_ps,'revenue_reversal')<expected_revenue-.01:alerts.append(dict(title='已完成订单履约金额未齐',severity='major',evidence=f'{key[1]} 的订单、退款与履约权益合计不一致，请核对原始记录',department='data',property_id=key[0],owner=o['owner'],due_date=asof,order_no=key[1]))
  ofs=[x for x in pastfs if (x['_property'],x['order_no'])==key];ops=[x for x in pastpay if (x['_property'],x['order_no'])==key];oc=[x for x in group['cost'] if (x['_property'],x['order_no'])==key and x['scope']=='park' and x['day']<=end]
  contract=contracts.get((key[0],o['contract_code']));base=total(ofs)-total(ops,'revenue_reversal');comm=0
  if contract:
   cb=base if contract['basis']=='fulfilled' else total([x for x in ops if x['type']=='collection'])-total([x for x in ops if x['type']=='refund']);comm=cb*contract['rate']
  if base-total(oc)-comm<0:alerts.append(dict(title='成熟订单已知贡献为负',severity='major',evidence=f'{key[1]} 履约净收入{base:.2f}－已关联成本{total(oc):.2f}－佣金{comm:.2f}；未分摊公共获客费用',department='finance',property_id=key[0],owner=o['owner'],due_date=asof,order_no=key[1]))
 customers={};all_customer_dates={}
 for x in pastfs:
  o=orders.get((x['_property'],x['order_no']))
  if o and o['customer_code']:all_customer_dates.setdefault(o['customer_code'],set()).add((x['day'],x['_property']+':'+o['order_no']))
 for code,visits in all_customer_dates.items():
  if any(within(d) for d,no in visits):customers[code]={'old':any(d<start for d,no in visits),'orders':len({no for d,no in visits})}
 entries=[x for x in group['operator_entry'] if within(x['day'])];operator_comm=total([x for x in commissions if x['beneficiary']=='operator']);op_rev=total([x for x in entries if x['type'] in ['service_revenue','goods_revenue','membership_fulfilled']]);op_cost=total([x for x in group['cost'] if within(x['day']) and x['scope']=='operator'])+total([x for x in entries if x['type']=='commission_expense'])
 result=dict(metrics={'revenue':revenue,'fulfilled_gross':gross,'revenue_reversal':reversal,'room_revenue':room_revenue,'room_nights':nights,'available':availability,'recorded_available':available,'occupancy':nights/availability if availability else None,'adr':room_revenue/nights if nights else None,'revpar':room_revenue/availability if availability else None,'trade_amount':total([x for x in group['order'] if within(x['order_date'])],'booking_amount'),'collections':collections,'refunds':refunds,'paid_net':round(collections-refunds,2),'received':round(receipts,2),'pending':round(pending,2),'principal_liability':round(principal_liability,2),'advance':round(advance,2),'receivable':round(receivable,2),'platform_fees_withheld':total([x for x in ps if x['type']=='platform_fee']),'cost':known_cost,'acquisition':spend,'commission':commission,'known_contribution':contribution,'contribution':contribution if cost_complete else None,'cost_complete':cost_complete,'inventory_complete':inventory_complete,'missing_inventory_days':len({(p,d) for p,d,t in expected-inv_keys}),'missing_cost_days':missing_cost,'new_customers':sum(not x['old'] for x in customers.values()),'returning_customers':sum(x['old'] for x in customers.values()),'repeat_customers':sum(x['orders']>1 for x in customers.values()),'unknown_customer_orders':sum(not orders[(x['property_id'],x['order_no'])]['customer_code'] for x in details)},orders=details,daily=daily,breakdown=breakdown,channels=channels,future=future,future_summary=future_summary,alerts=alerts,issues=issues,commissions=commissions,operator={'commission_revenue':operator_comm,'independent_revenue':op_rev,'total_revenue':round(operator_comm+op_rev,2),'recorded_cost':op_cost,'known_balance':round(operator_comm+op_rev-op_cost,2),'commission_received':total([x for x in entries if x['type']=='commission_received']),'note':'佣金为运营公司收入，园区总营收不再加一次。此处为所选项目归属，非净利润。'},targets=targets,operating_days=len({(x['_property'],x['day']) for x in inventory if x['is_open']}),updated_at=max((r['updated_at'] for r in rs),default=None),source='SQLite / 经授权录入及导入；未连接外部平台')


 # Hotel, room type, and actual operating-day classification are independently drillable.
 room_events=[dict(property_id=x['_property'],room_type=x.get('room_type') or 'unknown',day=x['day'],revenue=x['amount'],nights=x['room_nights']) for x in fs if x['business']=='room']
 for x in allocations:
  if within(x['day']) and x['business']=='room':room_events.append(dict(property_id=x['property_id'],room_type=x['room_type'],day=x['day'],revenue=-x['amount'],nights=0))
 day_types={}
 for x in inventory:day_types.setdefault((x['_property'],x['day']),set()).add(x['day_type'])
 def day_type(prop,d):
  values=day_types.get((prop,d),set())
  return next(iter(values)) if len(values)==1 else 'unknown'
 result['lodging_analysis']={}
 for dimension in ['property','room_type','day_type']:
  def event_key(x):return x['property_id'] if dimension=='property' else x['room_type'] if dimension=='room_type' else day_type(x['property_id'],x['day'])
  def inv_key(x):return x['_property'] if dimension=='property' else x['room_type'] if dimension=='room_type' else x['day_type']
  keys={event_key(x) for x in room_events}|{inv_key(x) for x in inventory}
  rows=[]
  for key in sorted(keys):
   ev=[x for x in room_events if event_key(x)==key];iv=[x for x in inventory if inv_key(x)==key];inc=round(sum(x['revenue'] for x in ev),2);night=sum(x['nights'] for x in ev);den=total(iv,'available') if iv and inventory_complete and key!='unknown' else None
   rows.append(dict(key=key,revenue=inc if ev else None,nights=night if ev else None,available=den,occupancy=night/den if ev and den else None,adr=inc/night if night else None,revpar=inc/den if ev and den else None))
  result['lodging_analysis'][dimension]=rows
 # Empty ledgers are unknown business performance, never fabricated zero actuals.
 if not fs and not any(x['revenue_reversal'] for x in ps):
  for k in ['revenue','fulfilled_gross','room_revenue','room_nights','contribution','known_contribution']:result['metrics'][k]=None
 if not group['order']:
  for k in ['trade_amount','collections','refunds','paid_net','received','pending','advance','principal_liability','receivable','new_customers','returning_customers','repeat_customers','unknown_customer_orders']:result['metrics'][k]=None
 # Restaurant/project costs are explicitly assigned; common costs stay unallocated.
 for b in result['breakdown']:
  selected=[x for x in fs if x['business']==b['business']]
  allocated=[x for x in costs if x.get('business')==b['business']]
  b['allocated_cost']=total(allocated) if allocated and all(x['amount'] is not None for x in allocated) else None
  b['known_contribution']=round(b['fulfilled_gross']-b['allocated_cost'],2) if selected and b['allocated_cost'] is not None else None
  if not selected:b['fulfilled_gross']=None;b['guests']=None
  elif any(x.get('guests') is None for x in selected):b['guests']=None

 result['campaign_performance']=[]
 for campaign in campaigns:
  keys={k for k,o in orders.items() if k[0]==campaign['_property'] and o['campaign_code']==campaign['code']}
  linked_fs=[x for x in fs if (x['_property'],x['order_no']) in keys]
  linked_ps=[x for x in ps if (x['_property'],x['order_no']) in keys]
  result['campaign_performance'].append({**campaign,'paid_orders':len({(x['_property'],x['order_no']) for x in linked_ps if x['type']=='collection'}),'reserved_orders':len({(x['_property'],x['order_no']) for x in group['reservation'] if (x['_property'],x['order_no']) in keys and within(x['day']) and x['status']=='confirmed'}),'fulfilled_orders':len({(x['_property'],x['order_no']) for x in linked_fs}),'fulfilled_revenue':round(total(linked_fs)-total(linked_ps,'revenue_reversal'),2),'refunds':total([x for x in linked_ps if x['type']=='refund'])})
 # Operator commission balances are cumulative; contract terms drive due dates.
 commission_balances=[]
 for ck,contract in contracts.items():
  if contract['beneficiary']!='operator':continue
  keys={k for k,o in orders.items() if k[0]==ck[0] and o['contract_code']==ck[1]}
  events=[]
  for k in keys:
   if contract['basis']=='fulfilled':
    events += [(x['day'],x['amount']*contract['rate']) for x in pastfs if (x['_property'],x['order_no'])==k]
    events += [(x['day'],-x['revenue_reversal']*contract['rate']) for x in pastpay if (x['_property'],x['order_no'])==k and x['type']=='refund']
   else:
    events += [(x['day'],x['amount']*contract['rate']*(1 if x['type']=='collection' else -1)) for x in pastpay if (x['_property'],x['order_no'])==k and x['type'] in ['collection','refund']]
  earned=round(sum(v for d,v in events),2)
  received=total([x for x in group['operator_entry'] if x['_property']==ck[0] and x['contract_code']==ck[1] and x['type']=='commission_received' and x['day']<=end])
  due=round(sum(v for d,v in events if v<0 or (date.fromisoformat(d)+timedelta(days=contract['settlement_days'])).isoformat()<end),2)
  commission_balances.append(dict(property_id=ck[0],contract_code=ck[1],earned=earned,received=received,pending=round(earned-received,2),overdue=max(round(due-received,2),0),settlement_days=contract['settlement_days']))
 result['operator']['balances']=commission_balances
 result['operator']['pending']=round(sum(x['pending'] for x in commission_balances),2)
 result['operator']['overdue']=round(sum(x['overdue'] for x in commission_balances),2)
 for b in commission_balances:
  if b['overdue']>0:result['alerts'].append(dict(title='运营公司合同佣金逾期',severity='major',evidence=f"合同 {b['contract_code']}，按{b['settlement_days']}天账期，逾期未收{b['overdue']:.2f}元；到账按合同先进先抵",department='finance',property_id=b['property_id'],owner='',due_date=asof,order_no=''))
 return business.augment(result,group,start,end,asof,allocations)

@app.get('/api/dashboard')
def dashboard(request:Request,dataset:str='actual',property_id:str='',start:str='',end:str='',asof:str=''):
 u=auth(request);end=end or TODAY();dateval(end);start=start or (date.fromisoformat(end)-timedelta(days=29)).isoformat();asof=asof or TODAY();dateval(asof)
 with db() as c:rs=records(c,dataset,props=allowed_props(c,u,dataset,property_id))
 result=metrics(rs,start,end,asof)
 if u['role']=='operations':
  for k in ['cost','acquisition','commission','known_contribution','contribution','received','pending','advance','principal_liability','receivable','platform_fees_withheld','collections','refunds','paid_net']:result['metrics'].pop(k,None)
  result['operator']=None;result['commissions']=[]
  result['target_comparisons']=[{k:v for k,v in x.items() if k not in ['cost','known_cost','cost_gap']} for x in result['target_comparisons']]
  result['products']=[{k:v for k,v in x.items() if k not in ['allocated_cost','known_contribution']} for x in result['products']]
  result['breakdown']=[{k:v for k,v in x.items() if k not in ['allocated_cost','known_contribution']} for x in result['breakdown']]
  result['issues']=[x for x in result['issues'] if x['department']!='finance']
  result['channels']=[{k:v for k,v in x.items() if k not in ['commission','linked_cost','known_contribution']} for x in result['channels']]
  result['orders']=[{k:v for k,v in x.items() if k not in ['paid_net','pending']} for x in result['orders']]
  result['alerts']=[x for x in result['alerts'] if x['department']!='finance']
 return result
@app.get('/api/order/{rid}')
def drill(rid:int,request:Request):
 u=auth(request)
 with db() as c:
  r=c.execute('SELECT * FROM records WHERE id=? AND kind="order"',(rid,)).fetchone()
  if not r:err('订单不存在',404)
  order=unpack(r);scope(u,order['dataset'],order['property_id'])
  related=[x for x in records(c,order['dataset'],props=[order['property_id']]) if x['data'].get('order_no')==order['data']['order_no']]
  if u['role']=='operations':related=[x for x in related if x['kind'] not in FINANCIAL]
  return {'order':order,'records':related}


@app.post('/api/alerts/assign')
async def assign_alert(request:Request):
 u=auth(request);b=await read_json(request);dataset=b.get('dataset','actual');prop=b.get('property_id','');scope(u,dataset,prop,'issue',True)
 snapshot=dashboard(request,dataset,b.get('scope_property',''),b.get('start',''),b.get('end',''),b.get('asof',''))
 alert=next((a for a in snapshot['alerts'] if a['alert_key']==b.get('alert_key')),None)
 if not alert:err('该异常已变化或已消失，请刷新后处理',409)
 if alert['property_id'] and alert['property_id']!=prop:err('异常归属项目不匹配',403)
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  prior=next((r for r in records(c,dataset,'issue',[prop]) if r['data'].get('alert_key')==alert['alert_key'] and r['data']['status']!='closed'),None)
  if prior:return {'id':prior['id'],'reused':True}
  data=dict(day=TODAY(),department=alert['department'],title=alert['title'],severity=alert['severity'],order_no=alert.get('order_no',''),evidence=alert['evidence'],owner=b.get('owner') or alert['owner'],due_date=b.get('due_date') or alert['due_date'],status='open',alert_key=alert['alert_key'])
  rid=save_record(c,u,'issue',dataset,prop,'ALERT-'+alert['alert_key']+'-'+secrets.token_hex(3),data);check_relations(c,dataset)
 return {'id':rid,'reused':False}

@app.post('/api/account/password')
async def change_password(request:Request):
 u=auth(request);b=await read_json(request)
 if u['demo']:err('演示会话不能修改真实密码',403)
 new=str(b.get('new_password',''))
 if not 12<=len(new)<=200:err('新密码需要12至200个字符')
 with db() as c:
  row=c.execute('SELECT * FROM users WHERE username=?',(u['username'],)).fetchone()
  if not hmac.compare_digest(password_hash(str(b.get('old_password','')),row['salt']),row['hash']):err('当前密码不正确',403)
  salt=secrets.token_hex(16);c.execute('UPDATE users SET salt=?,hash=? WHERE id=?',(salt,password_hash(new,salt),row['id']));c.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],));audit(c,u,'password_change',None,'actual','',{'username':u['username']})
 if u['username']=='admin':
  path=DATA/'admin-password.txt'
  if path.exists():path.unlink()
 response=JSONResponse({'ok':True,'reauthenticate':True});response.delete_cookie('hotel_session');return response

@app.put('/api/users/{uid}')
async def edit_user(uid:int,request:Request):
 u=auth(request);b=await read_json(request)
 if u['demo'] or u['role']!='admin':err('仅真实集团管理员可修改账号权限',403)
 role=b.get('role');props=b.get('properties');active=b.get('active',True)
 if not isinstance(role,str) or role not in ROLES or not isinstance(props,list) or not props or any(not isinstance(x,str) for x in props) or not isinstance(active,bool):err('角色、项目范围或启用状态无效')
 if role!='admin' and '*' in props:err('非集团管理员须指定具体项目')
 with db() as c:
  row=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
  if not row:err('账号不存在',404)
  known={r['property_id'] for r in records(c,'actual','property')}
  if any(p!='*' and p not in known for p in props):err('未知项目范围')
  if row['username']==u['username'] and (role!='admin' or not active or props!=json.loads(row['properties'])):err('请由另一位管理员调整当前账号权限，避免自锁')
  c.execute('UPDATE users SET role=?,properties=?,active=? WHERE id=?',(role,json.dumps(props),int(active),uid));c.execute('DELETE FROM sessions WHERE user_id=?',(uid,));audit(c,u,'user_permissions',None,'actual','',{'username':row['username'],'before':{'role':row['role'],'properties':json.loads(row['properties']),'active':bool(row['active'])},'after':{'role':role,'properties':props,'active':active}})
 return {'ok':True}

init_db()
import integrations, sys
integrations.install(sys.modules[__name__])
if __name__=='__main__':
 import uvicorn
 uvicorn.run(app,host=os.environ.get('HOST','0.0.0.0'),port=int(os.environ.get('PORT','3001')))
