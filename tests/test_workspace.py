import io
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import threading
import sys
import zipfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image,ImageDraw,ImageFont
import test_system as system
import capture_ocr
s=system.s

def picture(color='white'):
 out=io.BytesIO();Image.new('RGB',(80,60),color).save(out,format='PNG');return out.getvalue()

class WorkspaceTests(unittest.TestCase):
 def setUp(self):
  system.SystemTests.setUp(self)
  with s.db() as c:
   for table in ['work_messages','work_media','work_booked_documents','work_items']:c.execute('DELETE FROM '+table)
  self.staff=self.account('worker','staff',['bhl']);self.other=self.account('other-worker','staff',['bhl'])
  self.manager=self.account('supervisor','manager',['bhl']);self.finance=self.account('accountant','finance',['bhl'])
  self.foreign=self.account('other-store','manager',['jtw'])
 def account(self,name,role,props):
  password='Only-For-Isolated-Test-123!'
  response=self.client.post('/api/users',json={'username':name,'password':password,'role':role,'properties':props});self.assertEqual(response.status_code,200,response.text)
  client=TestClient(s.app);response=client.post('/api/login',json={'username':name,'password':password,'remember_device':True});self.assertEqual(response.status_code,200)
  if role=='staff':self.assertIn('Max-Age=2592000',response.headers['set-cookie'])
  return client
 def upload(self,client=None,content=None,filename='photo.png',status=200):
  response=(client or self.staff).post('/api/workspace/media?dataset=actual&property_id=bhl&filename='+filename,content=content or picture(),headers={'Content-Type':'application/octet-stream'})
  self.assertEqual(response.status_code,status,response.text if response.status_code!=200 else '');return response.json()
 def create(self,kind='inspection',client=None,media=None,key='case-1',severity='normal'):
  client=client or self.staff;media=media or self.upload(client)['id']
  body={'dataset':'actual','property_id':'bhl','kind':kind,'title':'检查/单据验收','note':'','department':'kitchen','severity':severity,'client_key':key,'media_ids':[media]}
  response=client.post('/api/workspace/items',json=body);self.assertEqual(response.status_code,200,response.text)
  iid=response.json()['id']
  if kind=='document':
   deadline=time.monotonic()+35
   while client.get('/api/workspace/items/'+str(iid)).json()['ocr_status'] in ['pending','processing']:
    if time.monotonic()>deadline:self.fail('Document worker did not finish')
    time.sleep(.05)
  return iid,body
 def get(self,iid,client=None):
  response=(client or self.client).get('/api/workspace/items/'+str(iid));self.assertEqual(response.status_code,200,response.text);return response.json()
 def test_staff_scope_private_media_and_retained_device_login(self):
  uploaded=self.upload();iid,_=self.create(media=uploaded['id'])
  self.assertEqual(self.other.get('/api/workspace/items/'+str(iid)).status_code,403)
  self.assertEqual(self.foreign.get('/api/workspace/items/'+str(iid)).status_code,403)
  self.assertEqual(self.other.get('/api/workspace/media/'+uploaded['id']).status_code,403)
  self.assertEqual(TestClient(s.app).get('/api/workspace/media/'+uploaded['id']).status_code,401)
  self.assertEqual(self.staff.get('/api/workspace/media/'+uploaded['id']+'?download=true').content,picture())
  self.assertEqual(self.other.get('/api/workspace/items?dataset=actual').json()['items'],[])
  self.assertEqual(self.staff.get('/api/dashboard?dataset=actual').status_code,403)
  self.assertEqual(self.staff.get('/api/records/payment?dataset=actual').status_code,403)
  self.assertEqual(set(self.staff.get('/api/schema').json()['schemas']),{'property'})
  self.assertEqual(self.staff.get('/api/records/property?dataset=actual').status_code,200)
  self.assertEqual(self.staff.get('/api/logs?dataset=actual').status_code,403)
  self.assertEqual(self.staff.get('/.runtime/private_media/anything.png').status_code,404)
 def test_photo_direction_assignment_remediation_review_loop(self):
  iid,_=self.create(severity='redline');url='/api/workspace/items/'+str(iid)
  self.assertEqual(self.staff.post(url+'/messages',json={'type':'direction','text':'员工伪造指令'}).status_code,403)
  self.assertEqual(self.client.post(url+'/messages',json={'type':'direction','text':'请在开餐前复洗并复查'}).status_code,200)
  row=self.get(iid)
  self.assertEqual(self.manager.post(url+'/assign',json={'version':row['version'],'owner':'worker','due_date':s.TODAY(),'severity':'redline'}).status_code,200)
  stale=self.manager.post(url+'/assign',json={'version':row['version'],'owner':'worker','due_date':s.TODAY(),'severity':'redline'});self.assertEqual(stale.status_code,409)
  row=self.get(iid,self.staff);photo=self.upload(self.staff,picture('green'))
  response=self.staff.post(url+'/remediation',json={'version':row['version'],'text':'已复洗并培训','media_ids':[photo['id']]});self.assertEqual(response.status_code,200,response.text)
  self.assertEqual(self.staff.post(url+'/review',json={'version':1,'text':'自行关闭','approved':True}).status_code,403)
  row=self.get(iid)
  response=self.client.post(url+'/review',json={'version':row['version'],'text':'复查照片和现场均通过','approved':True});self.assertEqual(response.status_code,200,response.text)
  row=self.get(iid);self.assertEqual(row['status'],'closed');self.assertEqual(row['issue']['reviewer'],'admin')
  self.assertEqual(len(row['media']),2);self.assertTrue(any(m['type']=='direction' for m in row['messages']))
  linked=self.client.get('/api/records/issue?dataset=actual&property_id=bhl').json()['records'][0]
  self.assertEqual(self.client.delete('/api/records/issue/'+str(linked['id'])+'?version='+str(linked['version'])).status_code,409)
 def test_document_archives_recognizes_and_only_finance_books_once(self):
  suggestion={'fields':{'amount':128.5,'day':s.TODAY(),'merchant':'演示商店','invoice_number':'DEMO000001','category':'supplies','document_class':'expense'},'needs_confirmation':True,'text':'模拟单据','engine':'local_ocr'}
  with patch('capture_ocr.analyze',return_value=suggestion):iid,body=self.create('document')
  row=self.get(iid);self.assertEqual(row['ocr_status'],'recognized');self.assertIsNone(row['cost_id'])
  with s.db() as c:self.assertEqual(len(s.records(c,'actual','cost')),0)
  self.assertTrue(self.staff.post('/api/workspace/items',json=body).json()['reused'])
  url='/api/workspace/items/'+str(iid)+'/book'
  payload={'version':row['version'],**suggestion['fields'],'confirmed_expense':True,'scope':'park'}
  self.assertEqual(self.staff.post(url,json=payload).status_code,403)
  self.assertEqual(self.finance.post(url,json={**payload,'document_class':'purchase'}).status_code,422)
  first=self.finance.post(url,json=payload);self.assertEqual(first.status_code,200,first.text)
  self.assertTrue(self.finance.post(url,json=payload).json()['reused'])
  with s.db() as c:
   costs=s.records(c,'actual','cost');self.assertEqual(len(costs),1);self.assertEqual(costs[0]['data']['amount'],128.5)
   self.assertEqual(s.records(c,'actual','coverage'),[]);self.assertEqual(s.records(c,'actual','payment'),[])
  with patch('capture_ocr.analyze',return_value=suggestion):second,_=self.create('document',media=self.upload()['id'],key='duplicate-doc')
  row=self.get(second);response=self.finance.post('/api/workspace/items/'+str(second)+'/book',json={**payload,'version':row['version']});self.assertEqual(response.status_code,409)
 def test_purchase_archive_is_not_cost_and_leaves_no_pending_finance_task(self):
  with patch('capture_ocr.analyze',return_value={'fields':{'document_class':'purchase'},'needs_confirmation':True}):iid,_=self.create('document')
  row=self.get(iid);url='/api/workspace/items/'+str(iid)+'/archive'
  self.assertEqual(self.staff.post(url,json={'version':row['version'],'document_class':'purchase'}).status_code,403)
  response=self.finance.post(url,json={'version':row['version'],'document_class':'purchase'});self.assertEqual(response.status_code,200,response.text)
  self.assertFalse(response.json()['cost_created']);self.assertEqual(self.get(iid)['status'],'archived');self.assertEqual(self.get(iid)['finance_class'],'purchase')
  with s.db() as c:self.assertEqual(s.records(c,'actual','cost'),[])
  self.assertEqual(self.finance.get('/api/workspace/items?dataset=actual').json()['summary']['documents_pending'],0)
 def test_platform_receipt_books_to_separate_commerce_cost_ledger(self):
  media=self.client.post('/api/workspace/media?dataset=actual&property_id=youxuan&filename=receipt.png',content=picture())
  self.assertEqual(media.status_code,200)
  with patch('capture_ocr.analyze',return_value={'fields':{'amount':38,'day':s.TODAY()},'needs_confirmation':True}):
   created=self.client.post('/api/workspace/items',json={'dataset':'actual','property_id':'youxuan','kind':'document','client_key':'select-receipt','media_ids':[media.json()['id']]})
   self.assertEqual(created.status_code,200);iid=created.json()['id'];deadline=time.monotonic()+10
   while self.get(iid)['ocr_status'] in ['pending','processing']:
    if time.monotonic()>deadline:self.fail('Receipt recognition timed out')
    time.sleep(.03)
  row=self.get(iid);body=dict(version=row['version'],document_class='expense',confirmed_expense=True,amount=38,day=s.TODAY(),category='other',commerce_category='packaging')
  first=self.client.post('/api/workspace/items/'+str(iid)+'/book',json=body);self.assertEqual(first.status_code,200,first.text)
  self.assertTrue(self.client.post('/api/workspace/items/'+str(iid)+'/book',json=body).json()['reused'])
  with s.db() as c:
   self.assertEqual(s.records(c,'actual','cost'),[])
   costs=s.records(c,'actual','commerce_cost');self.assertEqual(len(costs),1);self.assertEqual(costs[0]['data']['category'],'packaging');self.assertEqual(costs[0]['data']['amount'],38)
 def test_multiple_documents_queue_without_blocking_upload_or_losing_originals(self):
  release=threading.Event();ids=[]
  def delayed(files,data):
   release.wait(timeout=8)
   return {'fields':{'amount':12.5},'needs_confirmation':True,'text':'排队识别测试'}
  media=[self.upload(content=picture(color))['id'] for color in ['red','green','blue']]
  with patch('capture_ocr.analyze',side_effect=delayed):
   try:
    start=time.monotonic()
    for i,mid in enumerate(media):
     r=self.staff.post('/api/workspace/items',json={'dataset':'actual','property_id':'bhl','kind':'document','client_key':'queue-'+str(i),'media_ids':[mid]})
     self.assertEqual(r.status_code,200,r.text);ids.append(r.json()['id'])
    self.assertLess(time.monotonic()-start,4)
    self.assertTrue(all(self.get(i)['ocr_status'] in ['pending','processing'] for i in ids))
    with s.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM work_media WHERE item_id IS NOT NULL').fetchone()[0],3)
   finally:release.set()
   deadline=time.monotonic()+10
   while any(self.get(i)['ocr_status'] in ['pending','processing'] for i in ids):
    if time.monotonic()>deadline:self.fail('Queued readers did not finish')
    time.sleep(.03)
   self.assertTrue(all(self.get(i)['ocr_status']=='recognized' for i in ids))
 def test_same_document_cannot_be_expensed_again_in_another_property(self):
  suggestion={'fields':{'amount':20,'day':s.TODAY(),'merchant':'同一演示商户','invoice_number':'SAME-INVOICE'},'needs_confirmation':True}
  with patch('capture_ocr.analyze',return_value=suggestion):iid,_=self.create('document')
  row=self.get(iid);body={**suggestion['fields'],'category':'supplies','document_class':'expense','confirmed_expense':True,'version':row['version']}
  self.assertEqual(self.client.post('/api/workspace/items/'+str(iid)+'/book',json=body).status_code,200)
  response=self.client.post('/api/workspace/media?dataset=actual&property_id=jtw&filename=invoice.png',content=picture());self.assertEqual(response.status_code,200)
  with patch('capture_ocr.analyze',return_value=suggestion):
   response=self.client.post('/api/workspace/items',json={'dataset':'actual','property_id':'jtw','kind':'document','client_key':'different-property','media_ids':[response.json()['id']]})
   self.assertEqual(response.status_code,200);second=response.json()['id']
   deadline=time.monotonic()+10
   while self.get(second)['ocr_status'] in ['pending','processing']:
    if time.monotonic()>deadline:self.fail('Second document worker timed out')
    time.sleep(.03)
  row=self.get(second)
  result=self.client.post('/api/workspace/items/'+str(second)+'/book',json={**body,'version':row['version']});self.assertEqual(result.status_code,409)
 def test_upload_ownership_and_content_checks(self):
  other=self.upload(self.other)
  response=self.staff.post('/api/workspace/items',json={'dataset':'actual','property_id':'bhl','kind':'inspection','client_key':'steal','media_ids':[other['id']]})
  self.assertEqual(response.status_code,403)
  self.upload(content=b'<svg onload="alert(1)"></svg>',filename='fake.png',status=422)
  response=self.foreign.post('/api/workspace/media?dataset=actual&property_id=bhl&filename=photo.png',content=picture());self.assertEqual(response.status_code,403)
  before=self.client.get('/api/workspace/items?dataset=actual').json()['items'];self.assertEqual(before,[])
 def test_heic_original_is_retained_with_browser_jpeg_preview(self):
  if not capture_ocr.HEIC_READY:self.skipTest('HEIC dependency not installed in this Python environment')
  out=io.BytesIO();Image.new('RGB',(100,80),'green').save(out,format='HEIF');original=out.getvalue()
  uploaded=self.upload(content=original,filename='iphone.heic');self.assertEqual(uploaded['mime'],'image/heic');self.create(media=uploaded['id'])
  response=self.staff.get('/api/workspace/media/'+uploaded['id']);self.assertEqual(response.headers['content-type'],'image/jpeg');self.assertTrue(response.content.startswith(b'\xff\xd8'))
  raw=self.staff.get('/api/workspace/media/'+uploaded['id']+'?download=true');self.assertEqual(raw.content,original);self.assertIn('attachment',raw.headers['content-disposition'])
 def test_real_local_chinese_receipt_recognition(self):
  if not shutil.which('tesseract'):self.skipTest('Tesseract binary not installed')
  source=Path(__file__).resolve().parents[1]/'.runtime/ocr/tessdata'
  if not (source/'chi_sim.traineddata').exists():self.skipTest('Pinned Chinese model not installed')
  if not Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc').exists():self.skipTest('Chinese fixture font not installed')
  model=s.DATA/'ocr/tessdata';model.mkdir(parents=True,exist_ok=True)
  for name in ['chi_sim','eng']:shutil.copyfile(source/(name+'.traineddata'),model/(name+'.traineddata'))
  image=Image.new('RGB',(1600,700),'white');draw=ImageDraw.Draw(image)
  font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',58)
  for i,line in enumerate(['报销单','销售方: 演示商店','日期: 2026-11-07','TOTAL: 128.50','发票号码: 12345678901234567890']):draw.text((60,40+i*115),line,font=font,fill='black')
  buffer=io.BytesIO();image.save(buffer,format='PNG')
  uploaded=self.upload(content=buffer.getvalue());iid,_=self.create('document',media=uploaded['id'])
  row=self.get(iid);self.assertEqual(row['ocr_status'],'recognized',row['recognition'])
  self.assertEqual(row['recognition']['fields']['amount'],128.5,row['recognition'])
  self.assertEqual(row['recognition']['fields']['day'],'2026-11-07',row['recognition'])
  self.assertIsNone(row['cost_id'])
 def test_video_upload_and_authenticated_range_playback(self):
  if not shutil.which('ffmpeg'):self.skipTest('ffmpeg not installed')
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'sample.mp4'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x120:d=1','-an','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True)
   uploaded=self.upload(content=path.read_bytes(),filename='inspection.mp4');self.assertEqual(uploaded['mime'],'video/mp4')
   self.create(media=uploaded['id'])
   response=self.staff.get('/api/workspace/media/'+uploaded['id'],headers={'Range':'bytes=0-15'})
   self.assertEqual(response.status_code,206);self.assertEqual(len(response.content),16)
 def test_mov_browser_preview_keeps_original(self):
  if not shutil.which('ffmpeg'):self.skipTest('ffmpeg not installed')
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'phone.mov';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x120:d=1','-an','-c:v','libx264','-f','mov',str(path)],check=True,capture_output=True)
   original=path.read_bytes();uploaded=self.upload(content=original,filename='phone.mov');self.assertEqual(uploaded['mime'],'video/quicktime');self.create(media=uploaded['id'])
   response=self.staff.get('/api/workspace/media/'+uploaded['id']);self.assertEqual(response.status_code,200);self.assertEqual(response.headers['content-type'],'video/mp4')
   raw=self.staff.get('/api/workspace/media/'+uploaded['id']+'?download=true');self.assertEqual(raw.content,original)
 def test_full_backup_restore_preserves_private_originals_and_daily_uses_bundle(self):
  self.create()
  root=Path(__file__).resolve().parents[1];env={**os.environ,'HOTEL_DATA_DIR':str(s.DATA)}
  with tempfile.TemporaryDirectory() as folder:
   folder=Path(folder);backup=folder/'full.zip';dest=folder/'restored'
   command=[sys.executable,str(root/'scripts/backup_full.py'),str(backup)]
   result=subprocess.run(command,env=env,capture_output=True);self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(backup.stat().st_mode&0o777,0o600)
   with zipfile.ZipFile(backup) as z:self.assertEqual(len(z.namelist()),2)
   self.assertNotEqual(subprocess.run(command,env=env,capture_output=True).returncode,0)
   result=subprocess.run([sys.executable,str(root/'scripts/restore_full.py'),str(backup),str(dest)],capture_output=True)
   self.assertEqual(result.returncode,0,result.stderr)
   import sqlite3
   with sqlite3.connect(dest/'hotel.sqlite3') as c:
    self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0)
    self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    name,digest=c.execute('SELECT storage_name,sha256 FROM work_media').fetchone()
    path=dest/'private_media'/name;self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest);self.assertEqual(path.stat().st_mode&0o777,0o600)
   daily=folder/'daily'
   result=subprocess.run([sys.executable,str(root/'scripts/backup_daily.py'),str(daily)],env=env,capture_output=True);self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(len(list(daily.glob('*.zip'))),1)
   with zipfile.ZipFile(backup) as src,zipfile.ZipFile(folder/'bad.zip','w') as dst:
    for name in src.namelist():dst.writestr(name,src.read(name))
    dst.writestr('../escape','invalid')
   failed=subprocess.run([sys.executable,str(root/'scripts/restore_full.py'),str(folder/'bad.zip'),str(folder/'unsafe')],capture_output=True)
   self.assertNotEqual(failed.returncode,0);self.assertFalse((folder/'escape').exists());self.assertFalse((folder/'unsafe').exists())
