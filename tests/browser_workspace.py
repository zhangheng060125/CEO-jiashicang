"""Mobile employee capture -> CEO instruction -> assigned remediation; real OCR -> reviewed cost."""
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from PIL import Image,ImageDraw,ImageFont
from playwright.sync_api import sync_playwright
from runtime_support import isolated_server,ROOT

def photo(color='white'):
 out=io.BytesIO();Image.new('RGB',(300,200),color).save(out,format='PNG');return out.getvalue()

with isolated_server(HOTEL_ALLOW_DEMO='0') as (base,runtime),sync_playwright() as p:
 models=ROOT/'.runtime/ocr/tessdata';target=runtime/'ocr/tessdata';target.mkdir(parents=True)
 for name in ['eng','chi_sim']:shutil.copyfile(models/(name+'.traineddata'),target/(name+'.traineddata'))
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
 admin=browser.new_page(viewport={'width':1440,'height':1000});errors=[];admin.on('pageerror',lambda e:errors.append(str(e)))
 password=(runtime/'admin-password.txt').read_text().split('password: ',1)[1].strip()
 admin.goto(base);admin.locator('[name=username]').fill('admin');admin.locator('[name=password]').fill(password);admin.locator('#login-form button[type=submit]').click();admin.wait_for_selector('.metric')
 staff_password=secrets.token_urlsafe(20)
 for username,role in [('演示采购员','staff'),('演示餐厅主管','manager')]:
  result=admin.request.post(base+'/api/users',data={'username':username,'password':staff_password,'role':role,'properties':['bhl']});assert result.status==200,result.text()
 staff=browser.new_context(viewport={'width':390,'height':844}).new_page();staff.on('pageerror',lambda e:errors.append(str(e)))
 staff.context.grant_permissions(['microphone']);staff.goto(base+'/capture');staff.locator('[name=username]').fill('演示采购员');staff.locator('[name=password]').fill(staff_password);staff.locator('[name=remember_device]').check();staff.locator('#login-form button[type=submit]').click();staff.wait_for_selector('#capture-document')
 assert staff.locator('body').evaluate("e=>e.classList.contains('staff-mode')")
 assert staff.locator('[data-view]').count()==1
 assert staff.request.get(base+'/api/dashboard?dataset=actual').status==403
 image=Image.new('RGB',(1600,700),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',58)
 for i,line in enumerate(['报销单（测试样例）','销售方: 演示用品商店','日期: 2026-11-07','客用品 TOTAL: 128.50','发票号码: 12345678901234567890']):draw.text((50,35+i*115),line,font=font,fill='black')
 data=io.BytesIO();image.save(data,format='PNG')
 staff.locator('#capture-document').click();staff.locator('#work-camera-input').set_input_files({'name':'测试报销单.png','mimeType':'image/png','buffer':data.getvalue()});staff.locator('#work-record').click();staff.wait_for_function("document.querySelector('#work-record').textContent.includes('结束录音')");staff.wait_for_timeout(350);staff.locator('#work-record').click();staff.wait_for_function("document.querySelector('#work-selected-files').textContent.includes('语音')");staff.locator('#work-capture-form button[type=submit]').click();staff.wait_for_function("!document.querySelector('#modal').open")
 staff.wait_for_selector('[data-work-item]');receipt=staff.request.get(base+'/api/workspace/items?dataset=actual').json()['items'][0];receipt_id=receipt['id'];assert any(m['mime'].startswith('audio/') for m in receipt['media'])
 staff.locator('[data-work-item="'+str(receipt_id)+'"]').click();staff.wait_for_function("document.querySelector('#work-recognition')?.textContent.includes('128.5')",timeout=30000)
 assert staff.locator('#work-book').count()==0
 admin.locator('[data-view=workspace]').click();admin.wait_for_selector('[data-work-item]');admin.locator('[data-work-item="'+str(receipt_id)+'"]').click();admin.wait_for_selector('#work-book');admin.locator('#work-book').click();admin.wait_for_selector('#work-book-form')
 admin.locator('#work-book-form [name=document_class]').select_option('expense');admin.locator('#work-book-form [name=confirmed_expense]').check();admin.locator('#work-book-form button').click();admin.wait_for_function("document.querySelector('#modal-body').textContent.includes('已核对为实际费用')")
 costs=admin.request.get(base+'/api/records/cost?dataset=actual&property_id=bhl').json()['records'];assert len(costs)==1 and costs[0]['data']['amount']==128.5
 assert admin.request.get(base+'/api/records/payment?dataset=actual').json()['records']==[]
 staff.locator('#modal .close').click();staff.locator('#capture-inspection').click();staff.locator('#work-files-input').set_input_files({'name':'清洁检查-测试照片.png','mimeType':'image/png','buffer':photo('#d7e4cd')});staff.locator('#work-capture-form button[type=submit]').click();staff.wait_for_function("!document.querySelector('#modal').open");staff.wait_for_selector('[data-work-kind=inspection]')
 row=next(x for x in staff.request.get(base+'/api/workspace/items?dataset=actual').json()['items'] if x['kind']=='inspection');iid=row['id']
 admin.locator('#modal .close').click();admin.locator('#work-refresh').click();admin.wait_for_selector('[data-work-item="'+str(iid)+'"]');admin.locator('[data-work-item="'+str(iid)+'"]').click();admin.locator('#work-reply-form [name=text]').fill('请当班清洁并重新培训，上传整改照片后由主管复查。');admin.locator('#work-reply-form [name=direction]').check();admin.locator('#work-reply-form button').click();admin.wait_for_function("document.querySelector('.work-direction')!==null")
 admin.locator('#work-assign').click();admin.locator('#work-assign-form [name=owner]').select_option('演示采购员');admin.locator('#work-assign-form [name=severity]').select_option('redline');admin.locator('#work-assign-form button').click();admin.wait_for_selector('#work-remediate')
 staff.locator('#work-refresh').click();staff.wait_for_selector('[data-work-item="'+str(iid)+'"]');staff.locator('[data-work-item="'+str(iid)+'"]').click();staff.wait_for_selector('#work-remediate');assert '管理指令' in staff.locator('#modal-body').inner_text()
 staff.locator('#work-remediate').click();staff.locator('#work-camera-input').set_input_files({'name':'整改完成-测试照片.png','mimeType':'image/png','buffer':photo('#7b9e60')});staff.locator('#work-capture-form button[type=submit]').click();staff.wait_for_function("!document.querySelector('#modal').open")
 admin.locator('#modal .close').click();admin.locator('#work-refresh').click();admin.wait_for_selector('[data-work-item="'+str(iid)+'"]');admin.locator('[data-work-item="'+str(iid)+'"]').click();admin.wait_for_selector('#work-review');admin.locator('#work-review').click();admin.locator('#work-review-form [name=text]').fill('已核对现场和整改照片，复查通过。');admin.locator('#work-review-form button').click();admin.wait_for_function("document.querySelector('.work-detail-meta')?.textContent.includes('已关闭')")
 row=admin.request.get(base+'/api/workspace/items/'+str(iid)).json();assert row['issue']['status']=='closed' and len(row['media'])==2
 assert admin.locator('.work-message .work-message').count()==0
 assert admin.locator('.work-conversation > .work-message').count()==len(row['messages'])
 admin.screenshot(path=str(ROOT/'docs/workspace-desktop.png'),full_page=True)
 staff.locator('#work-refresh').click();staff.wait_for_selector('[data-work-item]');assert staff.evaluate('document.documentElement.scrollWidth<=innerWidth');staff.wait_for_function("document.querySelector('#toast').getBoundingClientRect().width===0 || !document.querySelector('#toast').classList.contains('visible')");staff.screenshot(path=str(ROOT/'docs/capture-mobile.png'),full_page=True)
 assert not errors,errors
 browser.close()
 print(json.dumps({'mobile_no_excel_capture':'PASS','voice_recording_upload':'PASS','real_chinese_ocr':'PASS','finance_confirmed_cost':'PASS','no_automatic_payment':'PASS','ceo_direction':'PASS','photo_remediation_review':'PASS','employee_scope':'PASS','mobile_layout':'PASS'}))
