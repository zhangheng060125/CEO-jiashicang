"""Illustrated collaboration and receipt samples; DEMO ONLY, no actual submissions."""
from datetime import timedelta,date
import hashlib
import json
import secrets
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import server as s

def seed():
 with s.db() as c:
  if c.execute("SELECT 1 FROM work_items WHERE dataset='demo' AND client_key='DEMO-WORK-INSPECTION'").fetchone():return
  actor={'username':'演示员工','role':'admin','properties':['bhl'],'demo':True,'_workspace':True};now=s.NOW();due=(date.fromisoformat(s.TODAY())+timedelta(days=1)).isoformat()
  def picture(item_id,name,lines):
   root=s.DATA/'private_media';root.mkdir(exist_ok=True,mode=0o700)
   ident=secrets.token_hex(16);path=root/(ident+'.jpg');image=Image.new('RGB',(1300,850),'#f5f5ed');draw=ImageDraw.Draw(image)
   font_path=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
   font=ImageFont.truetype(str(font_path),46) if font_path.exists() else ImageFont.load_default()
   for i,line in enumerate(lines):draw.text((65,65+i*105),line,font=font,fill='#254c3c')
   draw.rectangle((25,25,1275,825),outline='#a99b72',width=4);image.save(path,quality=85)
   c.execute('INSERT INTO work_media(id,dataset,property_id,uploaded_by,item_id,storage_name,original_name,mime,size,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(ident,'demo','bhl','演示员工',item_id,path.name,name,'image/jpeg',path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest(),now))
  def item(kind,title,status,key,note):
   return c.execute('INSERT INTO work_items(dataset,property_id,kind,title,note,department,severity,status,submitted_by,owner,due_date,ocr_status,client_key,payload_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('demo','bhl',kind,title,note,'kitchen','major',status,'演示员工','演示餐厅主管' if kind=='inspection' else '',due if kind=='inspection' else '','not_applicable' if kind=='inspection' else 'recognized',key,'demo',now,now)).lastrowid
  iid=item('inspection','演示：餐具清洁与摆台需复查','in_progress','DEMO-WORK-INSPECTION','演示提报：培训巡检时发现餐具清洁记录不完整，请主管安排整改。')
  picture(iid,'演示现场示意.jpg',['演示示意图 · 非实际现场','餐厅培训与清洁检查','问题：餐具清洁记录需复查','员工拍照 → 主管安排 → 复查','本图仅说明流程，不是现场证据'])
  rid=s.save_record(c,actor,'issue','demo','bhl','FIELD-'+str(iid),dict(day=s.TODAY(),department='kitchen',title='演示：餐具清洁与摆台需复查',severity='major',order_no='',evidence='演示示意图，见管理协同提报 #'+str(iid),owner='演示餐厅主管',due_date=due,status='in_progress',alert_key='FIELD:'+str(iid)))
  c.execute('UPDATE work_items SET issue_id=? WHERE id=?',(rid,iid))
  for author,role,typ,content in [('演示CEO','admin','direction','请餐厅主管在晚餐前复洗、补齐记录，并上传复查照片。'),('演示餐厅主管','manager','comment','已安排当班人员重新检查，并补做培训；完成后提交复查。')]:
   c.execute('INSERT INTO work_messages(item_id,author,role,type,text,created_at) VALUES(?,?,?,?,?,?)',(iid,author,role,typ,content,now))
  did=item('document','演示：客用品报销单','submitted','DEMO-WORK-DOCUMENT','演示识别字段，等待财务核对；不自动计入费用。')
  picture(did,'演示报销单.jpg',['报销单 · 演示样例','销售方：演示用品商店','日期：'+s.TODAY(),'TOTAL：128.50','发票号码：DEMO20260001','仅供体验 · 非真实发票'])
  recognition={'engine':'demo_snapshot','needs_confirmation':True,'fields':{'amount':128.5,'day':s.TODAY(),'merchant':'演示用品商店','invoice_number':'DEMO20260001','category':'supplies','document_class':'expense'},'text':'演示样例：用品报销128.50元，等待财务确认。','warnings':['以上为模拟识别结果；确认费用性质前不计入经营成本。']}
  c.execute('UPDATE work_items SET ocr_json=? WHERE id=?',(json.dumps(recognition,ensure_ascii=False),did))
 print('Collaboration demo seeded; only simulated records and clearly labelled illustrations.')

if __name__=='__main__':seed()
