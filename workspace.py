"""Private media, management conversations and reviewed document intake."""
import hashlib
import io
import json
import math
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
from datetime import date,timedelta,datetime,timezone
from pathlib import Path
import threading
import queue
import zipfile
from fastapi import Request
from fastapi.responses import FileResponse,Response
from PIL import Image,ImageOps
import capture_ocr

MANAGEMENT={'admin','executive','manager'}
FINANCE={'admin','finance'}
DEPARTMENTS={'frontdesk','rooms','dining','cleaning','kitchen','finance','marketing','data','water','spa','goods'}
MAX_BYTES=64*1024*1024
OCR_SLOTS=threading.BoundedSemaphore(2)
VIDEO_LOCKS={}
VIDEO_LOCKS_GUARD=threading.Lock()
WEB_VIDEOS=set()

def install(s):
 media_root=s.DATA/'private_media';media_root.mkdir(mode=0o700,exist_ok=True)
 with s.db() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS work_items(id INTEGER PRIMARY KEY,dataset TEXT NOT NULL,property_id TEXT NOT NULL,
   kind TEXT NOT NULL,title TEXT NOT NULL,note TEXT NOT NULL,department TEXT NOT NULL,severity TEXT NOT NULL,
   status TEXT NOT NULL,submitted_by TEXT NOT NULL,owner TEXT NOT NULL DEFAULT '',due_date TEXT NOT NULL DEFAULT '',
   issue_id INTEGER,cost_id INTEGER,ocr_status TEXT NOT NULL DEFAULT 'not_applicable',ocr_json TEXT NOT NULL DEFAULT '{}',
   remediation TEXT NOT NULL DEFAULT '',review_result TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,
   client_key TEXT NOT NULL,payload_hash TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
   UNIQUE(dataset,submitted_by,client_key));
  CREATE INDEX IF NOT EXISTS work_items_scope ON work_items(dataset,property_id,id);
  CREATE TABLE IF NOT EXISTS work_media(id TEXT PRIMARY KEY,dataset TEXT NOT NULL,property_id TEXT NOT NULL,
   uploaded_by TEXT NOT NULL,item_id INTEGER,message_id INTEGER,storage_name TEXT NOT NULL UNIQUE,
   original_name TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL,sha256 TEXT NOT NULL,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS work_messages(id INTEGER PRIMARY KEY,item_id INTEGER NOT NULL,author TEXT NOT NULL,
   role TEXT NOT NULL,type TEXT NOT NULL,text TEXT NOT NULL,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS work_booked_documents(dataset TEXT NOT NULL,property_id TEXT NOT NULL,digest TEXT NOT NULL,
   item_id INTEGER NOT NULL,cost_id INTEGER NOT NULL,PRIMARY KEY(dataset,property_id,digest));
  CREATE UNIQUE INDEX IF NOT EXISTS work_documents_global ON work_booked_documents(dataset,digest);
  ''')

 def text(value,label,limit=2000,required=False):
  if not isinstance(value,str) or len(value)>limit:s.err(label+'格式无效')
  value=value.strip()
  if required and not value:s.err(label+'不能为空')
  return value

 def project(c,u,dataset,prop):
  s.scope(u,dataset,prop)
  if not isinstance(prop,str) or not prop or not c.execute("SELECT 1 FROM records WHERE dataset=? AND property_id=? AND kind='property'",(dataset,prop)).fetchone():s.err('请选择有效项目')

 def can_see(u,row):
  if u['role'] in MANAGEMENT:return True
  if u['role']=='finance' and row['kind']=='document':return True
  return u['username'] in (row['submitted_by'],row['owner'])

 def item(c,u,iid):
  row=c.execute('SELECT * FROM work_items WHERE id=?',(iid,)).fetchone()
  if not row:s.err('记录不存在',404)
  s.scope(u,row['dataset'],row['property_id'])
  if not can_see(u,row):s.err('无权查看此记录',403)
  return row

 def media_path(row):
  name=row['storage_name']
  if not re.fullmatch(r'[a-f0-9]{32}\.[a-z0-9]+',name):s.err('附件存储信息无效',500)
  path=media_root/name
  if path.is_symlink() or path.resolve().parent!=media_root.resolve() or not path.is_file():s.err('附件文件缺失',404)
  return path

 def media_public(row):
  return {k:row[k] for k in ['id','original_name','mime','size','sha256','created_at','uploaded_by','message_id']}|{'url':'/api/workspace/media/'+row['id']}

 def packed(c,u,row):
  value=dict(row);value.pop('payload_hash');value.pop('client_key');value['recognition']=json.loads(value.pop('ocr_json'))
  value['media']=[media_public(r) for r in c.execute('SELECT * FROM work_media WHERE item_id=? ORDER BY created_at,id',(row['id'],))]
  value['messages']=[dict(r) for r in c.execute('SELECT * FROM work_messages WHERE item_id=? ORDER BY id',(row['id'],))]
  value['synthetic']=value['recognition'].get('engine')=='demo_snapshot'
  value['finance_class']=row['review_result'] if row['kind']=='document' else ''
  if row['issue_id']:
   issue=c.execute('SELECT payload FROM records WHERE id=? AND kind=\'issue\'',(row['issue_id'],)).fetchone()
   value['issue']=json.loads(issue['payload']) if issue else None
   if issue:value['status']=value['issue']['status']
  value['permissions']={'manage':u['role'] in MANAGEMENT,'book':u['role'] in FINANCE,'direct':u['role'] in {'admin','executive'}}
  return value

 def version(row,b):
  if type(b.get('version')) is not int or b['version']!=row['version']:s.err('记录已更新，请刷新后重试',409)

 def service_actor(u,prop):return {**u,'role':'admin','properties':[prop],'_workspace':True}

 def record_event(c,u,row,action,detail=None):
  s.audit(c,u,'workspace_'+action,None,row['dataset'],row['property_id'],{'item_id':row['id'],**(detail or {})})

 def message(c,u,row,kind,content):
  mid=c.execute('INSERT INTO work_messages(item_id,author,role,type,text,created_at) VALUES(?,?,?,?,?,?)',(row['id'],u['username'],u['role'],kind,content,s.NOW())).lastrowid
  c.execute('UPDATE work_items SET version=version+1,updated_at=? WHERE id=?',(s.NOW(),row['id']))
  record_event(c,u,row,kind,{'message_id':mid})
  return mid

 def bind_media(c,u,ids,row,mid=None):
  if not isinstance(ids,list) or len(ids)>5 or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):s.err('每次最多5个不同附件')
  for ident in ids:
   media=c.execute('SELECT * FROM work_media WHERE id=?',(ident,)).fetchone()
   if not media or media['uploaded_by']!=u['username'] or media['dataset']!=row['dataset'] or media['property_id']!=row['property_id'] or media['item_id'] is not None:s.err('附件归属或状态无效',403)
   if row['kind']=='document' and not (media['mime'].startswith(('image/','audio/')) or media['mime'] in ['application/pdf','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']):s.err('单据请上传照片、PDF或xlsx，录音可补充说明')
   c.execute('UPDATE work_media SET item_id=?,message_id=? WHERE id=?',(row['id'],mid,ident))

 def identify(path):
  with path.open('rb') as handle:head=handle.read(32)
  heic=head[4:8]==b'ftyp' and any(brand in head[8:32] for brand in (b'heic',b'heix',b'mif1',b'avif'))
  if head.startswith((b'\x89PNG',b'\xff\xd8\xff',b'RIFF')) or heic:
   try:
    with Image.open(path) as image:
     if image.width*image.height>30_000_000:s.err('照片过大，请缩小后上传')
     fmt=image.format;image.verify()
    kind={'PNG':('png','image/png'),'JPEG':('jpg','image/jpeg'),'WEBP':('webp','image/webp'),'HEIF':('heic','image/heic'),'AVIF':('avif','image/avif')}.get(fmt)
    if kind:return kind
   except Exception:pass
  if heic:s.err('暂时无法读取此照片，请使用拍照按钮或截图上传')
  if head.startswith(b'%PDF-'):return 'pdf','application/pdf'
  if head.startswith(b'PK\x03\x04'):
   try:
    with zipfile.ZipFile(path) as archive:
     if sum(x.file_size for x in archive.infolist())>30*1024*1024 or len(archive.infolist())>5000:s.err('Excel解压体积过大')
     if any(name.lower().endswith('vbaproject.bin') for name in archive.namelist()):s.err('不接受含宏的Excel，请导出PDF或普通xlsx')
     if {'[Content_Types].xml','xl/workbook.xml'}<=set(archive.namelist()):return 'xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
   except zipfile.BadZipFile:pass
  if head[4:8] in [b'ftyp',b'moov',b'wide'] or head.startswith((b'\x1aE\xdf\xa3',b'ID3',b'RIFF')) or head[:1]==b'\xff':
   if not shutil.which('ffprobe'):s.err('视频/录音检查组件未安装，请先上传照片')
   try:
    result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_entries','stream=codec_type:format=duration,format_name','-of','json',str(path)],capture_output=True,timeout=15)
    info=json.loads(result.stdout);types={x['codec_type'] for x in info.get('streams',[])}
    duration_raw=info.get('format',{}).get('duration');duration=0 if duration_raw in [None,'N/A'] else float(duration_raw)
    if result.returncode or not types.intersection({'audio','video'}) or not math.isfinite(duration) or duration<0 or duration>300:s.err('视频或录音格式无效，或超过5分钟')
    if 'video' in types:
     if head.startswith(b'\x1aE\xdf\xa3'):return 'webm','video/webm'
     if b'qt  ' in head or head[4:8] in [b'moov',b'wide']:return 'mov','video/quicktime'
     return 'mp4','video/mp4'
    if head[4:8]==b'ftyp':return 'm4a','audio/mp4'
    if head.startswith(b'RIFF'):return 'wav','audio/wav'
    return ('webm','audio/webm') if head.startswith(b'\x1aE\xdf\xa3') else ('mp3','audio/mpeg')
   except (ValueError,KeyError,subprocess.TimeoutExpired):s.err('无法验证视频或录音，请重新拍摄')
  s.err('请上传常用照片、PDF、xlsx，或MP4/WebM视频和录音；不支持网页和可执行文件')

 def video_preview(row,path):
  ident=row['id'];preview=media_root/(ident+'_preview.mp4')
  if ident in WEB_VIDEOS:return path,row['mime']
  with VIDEO_LOCKS_GUARD:lock=VIDEO_LOCKS.setdefault(ident,threading.Lock())
  with lock:
   if preview.is_file() and not preview.is_symlink():return preview,'video/mp4'
   if not shutil.which('ffmpeg'):return path,row['mime']
   temp=media_root/(ident+'_preview_'+secrets.token_hex(4)+'.part')
   try:
    probe=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_entries','stream=codec_type,codec_name','-of','json',str(path)],capture_output=True,timeout=15)
    streams=json.loads(probe.stdout).get('streams',[]);video=[r.get('codec_name') for r in streams if r.get('codec_type')=='video']
    if row['mime']!='video/quicktime' and video and all(c in ['h264','vp8','vp9','av1'] for c in video):WEB_VIDEOS.add(ident);return path,row['mime']
    result=subprocess.run(['ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(path),'-map','0:v:0','-map','0:a:0?','-vf','scale=w=1280:h=720:force_original_aspect_ratio=decrease:force_divisible_by=2','-c:v','libx264','-preset','veryfast','-crf','28','-c:a','aac','-movflags','+faststart','-f','mp4',str(temp)],capture_output=True,timeout=90)
    if result.returncode==0 and temp.exists():temp.chmod(0o600);temp.replace(preview);return preview,'video/mp4'
   except (ValueError,subprocess.TimeoutExpired):pass
   finally:temp.unlink(missing_ok=True)
   return path,row['mime']

 def recognize(iid,identity):
  OCR_SLOTS.acquire()
  try:
   with s.db() as c:
    row=c.execute('SELECT * FROM work_items WHERE id=?',(iid,)).fetchone()
    if not row or row['cost_id'] or (row['payload_hash'],row['created_at'])!=identity:return
    files=[(media_path(r),r['mime']) for r in c.execute('SELECT * FROM work_media WHERE item_id=?',(iid,)) if not r['mime'].startswith(('audio/','video/'))]
    c.execute("UPDATE work_items SET ocr_status='processing',version=version+1,updated_at=? WHERE id=?",(s.NOW(),iid))
   try:
    result=capture_ocr.analyze(files,s.DATA);status='recognized'
   except Exception as ex:
    result={'error':str(ex) if isinstance(ex,ValueError) else '识别未完成，原件已归档，可补拍或由财务核对','needs_confirmation':True};status='failed'
   with s.db() as c:
    changed=c.execute('UPDATE work_items SET ocr_status=?,ocr_json=?,version=version+1,updated_at=? WHERE id=? AND payload_hash=? AND created_at=?',(status,json.dumps(result,ensure_ascii=False),s.NOW(),iid,*identity))
    if changed.rowcount:s.audit(c,{'username':'本地OCR'},'workspace_recognized',None,row['dataset'],row['property_id'],{'item_id':iid,'status':status,'automatic_booking':False})
  finally:OCR_SLOTS.release()

 # A durable DB-backed queue: callbacks return promptly; two daemon workers process originals.
 jobs=queue.Queue();queued=set();queue_lock=threading.Lock();workers=[]
 def run_jobs():
  while True:
   task=jobs.get()
   if task is None:jobs.task_done();return
   iid,identity=task
   try:recognize(iid,identity)
   except Exception:
    with s.db() as c:c.execute("UPDATE work_items SET ocr_status='failed',ocr_json=? WHERE id=? AND payload_hash=? AND created_at=?",(json.dumps({'error':'读取未完成，原件已归档，请重试或人工核对'},ensure_ascii=False),iid,*identity))
   finally:
    with queue_lock:queued.discard(task)
    jobs.task_done()
 def schedule(iid=None):
  with queue_lock:
   if not workers:
    for i in range(2):
     worker=threading.Thread(target=run_jobs,name='document-reader-'+str(i),daemon=True);workers.append(worker);worker.start()
  with s.db() as c:
   rows=list(c.execute("SELECT id,payload_hash,created_at FROM work_items WHERE kind='document' AND cost_id IS NULL AND ocr_status IN ('pending','processing')")) if iid is None else list(c.execute("SELECT id,payload_hash,created_at FROM work_items WHERE id=? AND kind='document' AND cost_id IS NULL",(iid,)))
  with queue_lock:
   for row in rows:
    task=(row['id'],(row['payload_hash'],row['created_at']))
    if task not in queued:queued.add(task);jobs.put(task)
 s.app.router.add_event_handler('startup',schedule)

 @s.app.get('/api/workspace/config')
 def config(request:Request):
  u=s.auth(request)
  return {'recognition':capture_ocr.capability(s.DATA),'max_file_mb':64,'max_files':5,'manage':u['role'] in MANAGEMENT,'book':u['role'] in FINANCE,'direct':u['role'] in {'admin','executive'}}

 @s.app.get('/api/workspace/people')
 def people(request:Request,dataset:str,property_id:str):
  u=s.auth(request)
  with s.db() as c:
   project(c,u,dataset,property_id)
   if u['demo']:return {'people':[{'username':'演示负责人','role':'manager'},{'username':'演示员工','role':'staff'}]}
   rows=[dict(r) for r in c.execute('SELECT username,role,properties FROM users WHERE active=1')]
   return {'people':[{'username':r['username'],'role':r['role']} for r in rows if ('*' in json.loads(r['properties']) or property_id in json.loads(r['properties'])) and (u['role'] in MANAGEMENT or r['username']==u['username'])]}

 @s.app.post('/api/workspace/media')
 async def upload(request:Request,dataset:str,property_id:str,filename:str):
  u=s.auth(request)
  with s.db() as c:project(c,u,dataset,property_id)
  name=Path(filename.replace('\\','/')).name
  if not name or len(name)>160 or any(ord(x)<32 for x in name):s.err('文件名无效')
  ident=secrets.token_hex(16);temp=media_root/(ident+'.part');size=0;digest=hashlib.sha256();stored=None
  try:
   with temp.open('xb') as out:
    temp.chmod(0o600)
    async for chunk in request.stream():
     size+=len(chunk)
     if size>MAX_BYTES:s.err('每个文件最多64MB',413)
     out.write(chunk);digest.update(chunk)
   if not size:s.err('文件为空')
   ext,mime=identify(temp);stored=media_root/(ident+'.'+ext);temp.rename(stored)
   with s.db() as c:
    usage=c.execute('SELECT COALESCE(SUM(size),0) FROM work_media').fetchone()[0]
    if usage+size>int(os.environ.get('HOTEL_MEDIA_QUOTA_MB','2048'))*1024*1024:s.err('附件存储已达到配置上限，请联系管理员扩容',413)
    c.execute('INSERT INTO work_media(id,dataset,property_id,uploaded_by,storage_name,original_name,mime,size,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,dataset,property_id,u['username'],stored.name,name,mime,size,digest.hexdigest(),s.NOW()))
    s.audit(c,u,'workspace_upload',None,dataset,property_id,{'media_id':ident,'sha256':digest.hexdigest(),'bytes':size})
   return {'id':ident,'name':name,'mime':mime,'size':size,'sha256':digest.hexdigest()}
  except:
   temp.unlink(missing_ok=True)
   if stored:stored.unlink(missing_ok=True)
   raise

 @s.app.get('/api/workspace/media/{ident}')
 def attachment(ident:str,request:Request,download:bool=False):
  u=s.auth(request)
  with s.db() as c:
   row=c.execute('SELECT * FROM work_media WHERE id=?',(ident,)).fetchone()
   if not row:s.err('附件不存在',404)
   s.scope(u,row['dataset'],row['property_id'])
   if row['item_id']:item(c,u,row['item_id'])
   elif row['uploaded_by']!=u['username']:s.err('附件尚未提交，只有上传人可见',403)
   path=media_path(row)
  if row['mime'].startswith('image/') and not download:
   preview=media_root/(ident+'_preview.jpg')
   with VIDEO_LOCKS_GUARD:lock=VIDEO_LOCKS.setdefault(ident,threading.Lock())
   with lock:
    if not preview.is_file():
     image=ImageOps.exif_transpose(Image.open(path));image.thumbnail((1800,1800))
     rgba=image.convert('RGBA');canvas=Image.new('RGB',rgba.size,'white');canvas.paste(rgba,mask=rgba.getchannel('A'))
     temp=media_root/(ident+'_preview_'+secrets.token_hex(4)+'.part');canvas.save(temp,format='JPEG',quality=82);temp.chmod(0o600);temp.replace(preview)
   return FileResponse(preview,media_type='image/jpeg')
  if row['mime'].startswith('video/') and not download:
   view,mime=video_preview(row,path)
   return FileResponse(view,media_type=mime,content_disposition_type='inline')
  return FileResponse(path,media_type=row['mime'],filename=row['original_name'],content_disposition_type='attachment' if download or row['mime'] in ['application/pdf','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'] else 'inline')

 @s.app.get('/api/workspace/items')
 def listing(request:Request,dataset:str='actual',property_id:str='',offset:int=0):
  u=s.auth(request);s.scope(u,dataset,property_id)
  with s.db() as c:
   props=s.allowed_props(c,u,dataset,property_id)
   rows=[r for r in c.execute('SELECT * FROM work_items WHERE dataset=? ORDER BY id DESC',(dataset,)) if (props is None or r['property_id'] in props) and can_see(u,r)]
   if offset<0:s.err('分页参数无效')
   rows.sort(key=lambda r:(r['severity']=='redline' and r['status']!='closed',r['id']),reverse=True)
   summary={'inspection_open':sum(r['kind']=='inspection' and r['status']!='closed' for r in rows),'documents_pending':sum(r['kind']=='document' and not r['cost_id'] and r['status']!='archived' for r in rows),'redlines':sum(r['kind']=='inspection' and r['severity']=='redline' and r['status']!='closed' for r in rows)}
   return {'items':[packed(c,u,r) for r in rows[offset:offset+100]],'total':len(rows),'summary':summary}

 @s.app.get('/api/workspace/items/{iid}')
 def detail(iid:int,request:Request):
  u=s.auth(request)
  with s.db() as c:return packed(c,u,item(c,u,iid))

 @s.app.post('/api/workspace/items')
 async def create(request:Request):
  u=s.auth(request);b=await s.read_json(request);kind=b.get('kind');dataset=b.get('dataset');prop=b.get('property_id')
  if kind not in ['inspection','document']:s.err('提报类型无效')
  title=text(b.get('title',''),'标题',120) or ('现场提报' if kind=='inspection' else '单据上传')
  note=text(b.get('note',''),'说明');department=b.get('department','rooms');severity=b.get('severity','normal')
  key=text(b.get('client_key',''),'提交编号',100,True);ids=b.get('media_ids',[])
  if not isinstance(department,str) or department not in DEPARTMENTS or severity not in ['normal','major','redline']:s.err('部门或严重性无效')
  if not isinstance(ids,list) or not ids:s.err('请先拍照、录音或选择文件')
  digest=hashlib.sha256(json.dumps([kind,prop,title,note,department,severity,ids],ensure_ascii=False).encode()).hexdigest()
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE');project(c,u,dataset,prop)
   prior=c.execute('SELECT * FROM work_items WHERE dataset=? AND submitted_by=? AND client_key=?',(dataset,u['username'],key)).fetchone()
   if prior:
    if prior['payload_hash']!=digest:s.err('提交编号已使用且内容不同',409)
    return {'id':prior['id'],'reused':True}
   iid=c.execute('INSERT INTO work_items(dataset,property_id,kind,title,note,department,severity,status,submitted_by,ocr_status,client_key,payload_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(dataset,prop,kind,title,note,department,severity,'submitted',u['username'],'pending' if kind=='document' else 'not_applicable',key,digest,s.NOW(),s.NOW())).lastrowid
   row=item(c,u,iid);bind_media(c,u,ids,row)
   if kind=='document' and not c.execute("SELECT 1 FROM work_media WHERE item_id=? AND mime NOT LIKE 'audio/%' LIMIT 1",(iid,)).fetchone():s.err('请补一张单据照片或PDF/Excel，录音用于说明用途')
   record_event(c,u,row,'submitted',{'kind':kind,'media_ids':ids})
  if kind=='document':schedule(iid)
  return {'id':iid,'reused':False}

 @s.app.post('/api/workspace/items/{iid}/messages')
 async def reply(iid:int,request:Request):
  u=s.auth(request);b=await s.read_json(request);kind=b.get('type','comment');content=text(b.get('text',''),'反馈',2000);ids=b.get('media_ids',[])
  if kind not in ['comment','direction'] or kind=='direction' and u['role'] not in {'admin','executive'}:s.err('无权发布此类指令',403)
  if not content and not ids:s.err('请说一句话、录音或上传附件')
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE');row=item(c,u,iid);mid=message(c,u,row,kind,content);bind_media(c,u,ids,row,mid)
  return {'ok':True}

 @s.app.post('/api/workspace/items/{iid}/assign')
 async def assign(iid:int,request:Request):
  u=s.auth(request);b=await s.read_json(request)
  if u['role'] not in MANAGEMENT:s.err('仅管理人员可指派',403)
  owner=text(b.get('owner',''),'负责人',60,True);due=s.dateval(b.get('due_date',''));severity=b.get('severity','major')
  if severity not in ['normal','major','redline']:s.err('严重性无效')
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE');row=item(c,u,iid);version(row,b)
   if row['kind']!='inspection' or row['status']=='closed':s.err('此记录不能指派')
   department=b.get('department',row['department'])
   if not isinstance(department,str) or department not in DEPARTMENTS:s.err('请选择有效部门')
   if row['severity']=='redline' and severity!='redline':s.err('已报告红线不能降级')
   if not u['demo']:
    person=c.execute('SELECT properties FROM users WHERE username=? AND active=1',(owner,)).fetchone()
    if not person or not ({'*',row['property_id']} & set(json.loads(person['properties']))):s.err('负责人未获授权此项目')
   existing=c.execute('SELECT * FROM records WHERE id=?',(row['issue_id'],)).fetchone() if row['issue_id'] else None
   data=json.loads(existing['payload']) if existing else dict(day=datetime.fromisoformat(row['created_at']).astimezone(timezone(timedelta(hours=8))).date().isoformat(),department=row['department'],title=row['title'],evidence='现场提报 #'+str(iid)+'；附件见管理协同空间',order_no='',status='open',alert_key='FIELD:'+str(iid))
   data.update(owner=owner,due_date=due,severity=severity,status='in_progress',department=department)
   rid=s.save_record(c,service_actor(u,row['property_id']),'issue',row['dataset'],row['property_id'],existing['external_id'] if existing else 'FIELD-'+str(iid),data,existing['id'] if existing else None,existing['version'] if existing else None)
   c.execute('UPDATE work_items SET owner=?,due_date=?,severity=?,status=?,issue_id=?,department=? WHERE id=?',(owner,due,severity,'in_progress',rid,department,iid));message(c,u,row,'assignment','指派给 '+owner+'，截止 '+due)
  return {'ok':True,'issue_id':rid}

 @s.app.post('/api/workspace/items/{iid}/remediation')
 async def remediate(iid:int,request:Request):
  u=s.auth(request);b=await s.read_json(request);content=text(b.get('text',''),'整改说明',2000);ids=b.get('media_ids',[])
  if not content and not ids:s.err('请提交整改说明、照片或录音')
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE');row=item(c,u,iid);version(row,b)
   if row['kind']!='inspection' or not row['issue_id'] or row['status']=='closed':s.err('请先由主管指派整改')
   if u['role'] not in MANAGEMENT and u['username']!=row['owner']:s.err('只有负责人可提交整改',403)
   mid=message(c,u,row,'remediation',content);bind_media(c,u,ids,row,mid)
   evidence=content or '整改附件/录音见反馈 #'+str(mid)
   issue=c.execute('SELECT * FROM records WHERE id=?',(row['issue_id'],)).fetchone();data=json.loads(issue['payload']);data.update(status='review',remediation=evidence)
   s.save_record(c,service_actor(u,row['property_id']),'issue',row['dataset'],row['property_id'],issue['external_id'],data,issue['id'],issue['version'])
   c.execute("UPDATE work_items SET status='review',remediation=? WHERE id=?",(evidence,iid))
  return {'ok':True}

 @s.app.post('/api/workspace/items/{iid}/review')
 async def review(iid:int,request:Request):
  u=s.auth(request);b=await s.read_json(request);content=text(b.get('text',''),'复查结果',2000,True)
  if u['role'] not in MANAGEMENT:s.err('仅管理人员可复查',403)
  approved=b.get('approved')
  if not isinstance(approved,bool):s.err('复查选择无效')
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE');row=item(c,u,iid);version(row,b)
   if row['status']!='review' or not row['issue_id']:s.err('请先提交整改后再复查')
   latest=c.execute("SELECT author FROM work_messages WHERE item_id=? AND type='remediation' ORDER BY id DESC LIMIT 1",(iid,)).fetchone()
   if row['severity']=='redline' and latest and latest['author']==u['username']:s.err('红线须由另一位管理者复查')
   issue=c.execute('SELECT * FROM records WHERE id=?',(row['issue_id'],)).fetchone();data=json.loads(issue['payload']);data.update(status='closed' if approved else 'in_progress',review_result=content,reviewer=u['username'])
   s.save_record(c,service_actor(u,row['property_id']),'issue',row['dataset'],row['property_id'],issue['external_id'],data,issue['id'],issue['version'])
   c.execute('UPDATE work_items SET status=?,review_result=? WHERE id=?',(data['status'],content,iid));message(c,u,row,'review',('复查通过：' if approved else '继续整改：')+content)
  return {'ok':True}

 @s.app.post('/api/workspace/items/{iid}/recognize')
 async def retry(iid:int,request:Request):
  u=s.auth(request)
  with s.db() as c:
   row=item(c,u,iid)
   if row['kind']!='document' or row['cost_id']:s.err('此记录不需要重新识别')
   if row['ocr_status'] in ['pending','processing'] and row['updated_at']>(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat():return {'queued':True}
   c.execute("UPDATE work_items SET ocr_status='pending' WHERE id=?",(iid,))
  schedule(iid);return {'queued':True}

 @s.app.post('/api/workspace/items/{iid}/book')
 async def book(iid:int,request:Request):
  u=s.auth(request);b=await s.read_json(request)
  if u['role'] not in FINANCE:s.err('仅财务或集团管理员可确认入账',403)
  if b.get('confirmed_expense') is not True or b.get('document_class')!='expense':s.err('请确认这是实际费用；采购入库、资产和付款凭证先归档核对')
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE');row=item(c,u,iid)
   if row['cost_id']:
    if not c.execute("SELECT 1 FROM records WHERE id=? AND kind='cost'",(row['cost_id'],)).fetchone():s.err('关联费用已被删除，请财务核对处理',409)
    return {'cost_id':row['cost_id'],'reused':True}
   version(row,b)
   if row['kind']!='document' or row['ocr_status'] in ['pending','processing']:s.err('请等待识别完成，或失败后由财务人工核对')
   merchant=text(b.get('merchant',''),'供应商',100);invoice=text(b.get('invoice_number',''),'发票号码',60)
   digests=['file:'+r['sha256'] for r in c.execute("SELECT sha256 FROM work_media WHERE item_id=? AND mime NOT LIKE 'audio/%' AND mime NOT LIKE 'video/%'",(iid,))]
   if invoice:digests.append('invoice:'+re.sub(r'\s','',merchant+':'+invoice).lower())
   for digest in digests:
    if c.execute('SELECT 1 FROM work_booked_documents WHERE dataset=? AND digest=?',(row['dataset'],digest)).fetchone():s.err('此单据已入账，不能跨项目重复计费；共同费用须由财务核对分摊',409)
   data={'day':b.get('day'),'category':b.get('category'),'amount':b.get('amount'),'scope':b.get('scope','park'),'order_no':b.get('order_no',''),'business':b.get('business',''),'product_code':'','note':f'单据归档 #{iid}；财务确认：{u["username"]}；{merchant}；票号{invoice}'}
   clean=s.validate('cost',data)
   if clean['amount'] is None:s.err('必须确认实际金额，未知不能填0')
   rid=s.save_record(c,u,'cost',row['dataset'],row['property_id'],'DOCUMENT-'+str(iid),clean);s.check_relations(c,row['dataset'])
   for digest in set(digests):c.execute('INSERT INTO work_booked_documents VALUES(?,?,?,?,?)',(row['dataset'],row['property_id'],digest,iid,rid))
   c.execute("UPDATE work_items SET cost_id=?,status='booked',review_result='expense' WHERE id=?",(rid,iid));message(c,u,row,'booking',f'已核对为实际费用并关联成本记录 #{rid}；未自动确认收付款或全部成本完整')
  return {'cost_id':rid,'reused':False}

 @s.app.post('/api/workspace/items/{iid}/archive')
 async def archive_document(iid:int,request:Request):
  u=s.auth(request);b=await s.read_json(request)
  if u['role'] not in FINANCE:s.err('仅财务或集团管理员可确认单据分类',403)
  category=b.get('document_class');labels={'purchase':'采购入库','asset':'资产资料','payment':'付款凭证','other':'其他归档'}
  if not isinstance(category,str) or category not in labels:s.err('请选择非费用的归档类别')
  with s.db() as c:
   c.execute('BEGIN IMMEDIATE');row=item(c,u,iid);version(row,b)
   if row['kind']!='document' or row['cost_id']:s.err('已计入费用的单据需由财务在费用台账核对更正，不能直接改为归档')
   c.execute("UPDATE work_items SET status='archived',review_result=? WHERE id=?",(category,iid));message(c,u,row,'classification','财务确认为'+labels[category]+'，原件已归档，不计入当日经营费用。')
  return {'ok':True,'cost_created':False,'document_class':category}

 return {'recognize':schedule,'pack':packed,'media_root':media_root}
