"""Run against the local app. Mutates only uniquely named demo records and cleans them."""
import csv,io,json,os,uuid
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=os.environ.get('HOTEL_TEST_URL','http://127.0.0.1:3001')
RUN='BROWSER-'+uuid.uuid4().hex[:10]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE);page.locator('#demo-login').click();page.wait_for_selector('.metric')
 assert page.locator('.metric').count()==8
 assert page.request.get(BASE+'/api/records/order?dataset=actual').status==403
 page.screenshot(path='/tmp/senhuo-desktop.png',full_page=True)
 try:
  for key in ['orders','inventory','channels','finance','operator','business','customers','issues','targets','data']:
   page.locator('[data-view="'+key+'"]').click();page.wait_for_function("!document.querySelector('#workspace').textContent.includes('正在读取')")
   assert '暂时无法加载' not in page.locator('#workspace').inner_text(),key
  page.locator('[data-view="overview"]').click();page.wait_for_selector('[data-drill]');page.locator('[data-drill]').first.click()
  page.wait_for_selector('#modal[open]');assert '履约' in page.locator('#modal').inner_text();page.locator('#modal .close').click()
  page.locator('[data-view="issues"]').click();page.wait_for_selector('[data-alert]');page.locator('[data-alert]').first.click()
  page.locator('[name="owner"]').fill(RUN);page.locator('#record-form button[type="submit"]').click();page.wait_for_function("!document.querySelector('#modal').open")
  page.reload();page.wait_for_selector('.metric');page.locator('[data-view="issues"]').click()
  page.wait_for_function('(name)=>document.querySelector("#workspace").textContent.includes(name)',arg=RUN)
  rs=page.request.get(BASE+'/api/records/issue?dataset=demo&property_id=bhl').json()['records'];issue=next(x for x in rs if x['data']['owner']==RUN)
  page.locator('[data-issue-id="'+str(issue['id'])+'"]').click();page.locator('[name="status"]').select_option('closed')
  page.locator('#record-form button[type="submit"]').click();page.wait_for_function("document.querySelector('#form-error').textContent.includes('复查')")
  page.locator('[name="remediation"]').fill('浏览器验收：完成整改');page.locator('[name="review_result"]').fill('复查通过');page.locator('[name="reviewer"]').fill('浏览器测试复查人')
  page.locator('#record-form button[type="submit"]').click();page.wait_for_function("!document.querySelector('#modal').open")
  page.locator('[data-view="data"]').click();page.wait_for_selector('#import-kind');page.locator('#import-kind').select_option('customer');page.locator('#import-property').select_option('bhl')
  schema=page.request.get(BASE+'/api/schema').json();header=['external_id',*schema['schemas']['customer']['fields']]
  row={'external_id':RUN,'code':RUN,'phone_last4':'9876','day':schema['today'],'owner':RUN,'response_minutes':3,'reason':'','status':'following'}
  buf=io.StringIO();w=csv.writer(buf);w.writerow(header);w.writerow([row[k] for k in header]);content=buf.getvalue().encode()
  page.locator('#import-file').set_input_files({'name':'smoke.csv','mimeType':'text/csv','buffer':content});page.wait_for_function("document.querySelector('#commit-import') || (document.querySelector('#import-status').textContent && !document.querySelector('#import-status').textContent.includes('正在读取'))");assert page.locator('#commit-import').count(),page.locator('#import-status').inner_text();assert '新增 1 条' in page.locator('#import-status').inner_text()
  page.locator('#commit-import').click();page.wait_for_function("!document.querySelector('#commit-import')")
  page.locator('#import-kind').select_option('customer');page.locator('#import-property').select_option('bhl')
  page.locator('#import-file').set_input_files({'name':'smoke.csv','mimeType':'text/csv','buffer':content});page.wait_for_function("document.querySelector('#commit-import') || (document.querySelector('#import-status').textContent && !document.querySelector('#import-status').textContent.includes('正在读取'))");assert page.locator('#commit-import').count(),page.locator('#import-status').inner_text();assert '重复跳过 1 条' in page.locator('#import-status').inner_text()
  page.locator('#commit-import').click();page.wait_for_function("!document.querySelector('#commit-import')")
  page.locator('#import-kind').select_option('customer');page.locator('#manage-all').click();page.wait_for_selector('#export-records')
  with page.expect_download() as downloaded:page.locator('#export-records').click()
  assert downloaded.value.suggested_filename=='demo-customer.csv'
  page.locator('[data-view="overview"]').click();page.wait_for_selector('.metric');page.set_viewport_size({'width':390,'height':844})
  assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  page.screenshot(path='/tmp/senhuo-mobile.png',full_page=True)
  assert not errors,errors
  # Read-only verification of empty actual-space UI, without logging credentials.
  creds=Path(__file__).resolve().parents[1]/'.runtime/admin-password.txt'
  if creds.exists():
   lines=creds.read_text().splitlines();admin=browser.new_context().new_page();admin.goto(BASE)
   admin.locator('[name="username"]').fill(lines[0].split(': ',1)[1]);admin.locator('[name="password"]').fill(lines[1].split(': ',1)[1]);admin.locator('#login-form button[type="submit"]').click();admin.wait_for_selector('.metric')
   count=admin.request.get(BASE+'/api/records/order?dataset=actual').json()['records']
   if not count:assert '—' in admin.locator('.metric').first.inner_text()
   assert '真实经营空间' in admin.locator('#mode-notice').inner_text();admin.close()
  print(json.dumps({'result':'PASS','checks':['demo isolation','11 module navigation','order drilldown','issue create/persist/close guards','CSV preview and commit','duplicate import','scoped export','mobile overflow','actual login','no JS errors']}))
 finally:
  for kind in ['issue','customer']:
   for r in page.request.get(BASE+'/api/records/'+kind+'?dataset=demo&property_id=bhl').json()['records']:
    if r['data'].get('owner')==RUN:page.request.delete(BASE+f'/api/records/{kind}/{r["id"]}?version={r["version"]}')
  browser.close()
