"""Browser acceptance for the added management workflows, demo-only with cleanup."""
from playwright.sync_api import sync_playwright
import os,json,uuid
BASE=os.environ.get('HOTEL_TEST_URL','http://127.0.0.1:3001');RUN='EXT-'+uuid.uuid4().hex[:8]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE);page.locator('#demo-login').click();page.wait_for_selector('.metric')
 def open_type(kind):
  page.locator('[data-view="data"]').click();page.wait_for_selector('#import-kind');page.locator('#import-kind').select_option(kind);page.locator('#manage-all').click();page.wait_for_selector('#new-record')
 def field(name,value):
  selector=page.locator('[name="'+name+'"]')
  if selector.evaluate('(e)=>e.tagName')=='SELECT':selector.select_option(value)
  else:selector.fill(value)
 def create(kind,values):
  open_type(kind);page.locator('#new-record').click();page.wait_for_selector('#record-form');field('_property','bhl');field('_external',RUN+'-'+kind)
  for key,value in values.items():field(key,str(value))
  page.locator('#record-form button[type="submit"]').click();page.wait_for_function("!document.querySelector('#modal').open")
 try:
  create('alert_rule',dict(code='refund_ratio',channel=RUN,enabled='true',threshold='.6',severity='major',owner=RUN,deadline_days='3'))
  page.reload();page.wait_for_selector('.metric');open_type('alert_rule');assert RUN in page.locator('#workspace').inner_text()
  create('sop_item',dict(code=RUN,department='kitchen',title='浏览器检查标准 '+RUN,standard='记录必须完整',redline='false',active='true'))
  today=page.request.get(BASE+'/api/health').json()['today']
  create('sop_check',dict(day=today,item_code=RUN,result='fail',evidence='浏览器测试检查证据',owner=RUN,due_date=today))
  issues=page.request.get(BASE+'/api/records/issue?dataset=demo&property_id=bhl').json()['records'];generated=[r for r in issues if r['data'].get('alert_key')=='SOP:'+RUN+'-sop_check'];assert len(generated)==1
  page.locator('[data-view="issues"]').click();page.wait_for_function('(r)=>document.querySelector("#workspace").textContent.includes(r)',arg=RUN)
  assert '合格率' in page.locator('#workspace').inner_text()
  create('review',dict(day=today,channel=RUN,rating='4',category='service',content='响应13800138000，test@example.com',owner=RUN,response='已回复',status='responded'))
  reviews=page.request.get(BASE+'/api/records/review?dataset=demo&property_id=bhl').json()['records'];review=next(r for r in reviews if r['external_id']==RUN+'-review');assert '13800138000' not in review['data']['content']
  page.locator('[data-view="channels"]').click();page.wait_for_function("document.querySelector('#workspace').textContent.includes('同批匿名观看客户转化')")
  assert 'DEMO-COHORT' in page.locator('#workspace').inner_text()
  page.locator('[data-view="retail"]').click();page.wait_for_function("document.querySelector('#workspace').textContent.includes('会员与预售券权益余额')")
  assert 'DEMO-RIGHT-2' in page.locator('#workspace').inner_text()
  page.locator('[data-view="targets"]').click();page.wait_for_function("document.querySelector('#workspace').textContent.includes('逐项目 / 渠道目标差异')")
  assert not errors,errors
  print(json.dumps({'extensions':'PASS','checks':['rule editor persistence','SOP failed check auto task','review masking','cohort view','entitlement ledger','budget variance view','no JS errors']}))
 finally:
  for kind in ['issue','sop_check','sop_item','review','alert_rule']:
   rs=page.request.get(BASE+'/api/records/'+kind+'?dataset=demo&property_id=bhl').json()['records']
   for r in rs:
    if r['external_id'].startswith(RUN) or r['data'].get('alert_key')=='SOP:'+RUN+'-sop_check':
     response=page.request.delete(BASE+f'/api/records/{kind}/{r["id"]}?version={r["version"]}');assert response.status==200,response.text()
  browser.close()
