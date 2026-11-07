"""Verify the real public Pages site with TLS-verified HTTP responses rendered in Chromium.
The HTTP bridge keeps the managed proxy/CA trust and does not substitute local files.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from playwright.sync_api import sync_playwright

url=os.environ.get('HOTEL_PAGES_URL','https://zhangheng060125.github.io/CEO-jiashicang/?v=1.7.0')
origin=urlsplit(url).netloc
out=Path(os.environ.get('HOTEL_PAGES_SCREENSHOT','/tmp/senhuo-pages-live.png'))
with httpx.Client(timeout=30,follow_redirects=True) as client,sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];failures=[];urls=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 def remote(route):
  target=route.request.url
  if urlsplit(target).netloc!=origin:
   route.abort();return
  response=client.request(route.request.method,target)
  urls.append(target)
  if response.status_code>=400 and not target.endswith('favicon.ico'):failures.append([response.status_code,target])
  headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-encoding','content-length','transfer-encoding','connection')}
  route.fulfill(status=response.status_code,headers=headers,body=response.content)
 page.route('https://**/*',remote)
 try:
  page.goto(url);page.wait_for_selector('#preview-enter:not([disabled])',timeout=30000)
  page.locator('#preview-enter').click();page.wait_for_selector('.metric')
  assert page.locator('.metric').count()==8
  assert '只读' in page.locator('#source-label').inner_text()
  page.locator('#preview-guide').click();page.locator('[data-preview-step="1"]').click()
  page.locator('#preview-action').click();page.wait_for_selector('#modal[open]')
  assert '订单下钻' in page.locator('#modal').inner_text();page.locator('#modal .close').click()
  page.locator('[data-view="overview"]').click();page.wait_for_selector('.metric')
  page.locator('#property-filter').select_option('bhl');page.wait_for_selector('.metric')
  page.locator('#preview-period').select_option('7');page.wait_for_selector('.metric')
  page.locator('#preview-reset').click();page.wait_for_selector('.metric');page.wait_for_function("!document.querySelector('#preview-action').disabled")
  page.locator('#property-filter').select_option('bhcs');page.wait_for_selector('.sector-metrics[data-sector=dining]')
  assert all(w not in page.locator('#workspace').inner_text() for w in ['入住率','RevPAR','ADR'])
  expected=client.get(url.split('?')[0]+'demo/report-bhcs-30.json?v=1.7.0').json()['sectors']['dining']['metrics']['revenue']
  assert f'{expected:,.0f}' in page.locator('.metric').first.inner_text()
  out.parent.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(out),full_page=False)
  page.locator('#property-filter').select_option('water');page.wait_for_selector('.sector-metrics[data-sector=water]');assert '日接待承载利用率' in page.locator('#workspace').inner_text()
  page.locator('#property-filter').select_option('');page.wait_for_selector('.metric')
  page.locator('[data-view=workspace]').click();page.wait_for_selector('[data-work-kind=document]');page.locator('[data-work-kind=document]').click();page.wait_for_selector('#work-recognition');assert '128.5' in page.locator('#work-recognition').inner_text();assert page.locator('#work-book').count()==0;page.locator('#modal .close').click()
  page.locator('[data-work-kind=inspection]').click();page.wait_for_selector('#modal[open]');assert '管理指令' in page.locator('#modal-body').inner_text();page.locator('#modal .close').click()
  page.goto(url+'&capture=1');page.wait_for_selector('#capture-inspection');assert '管理协同' in page.locator('#page-title').inner_text()
  out.parent.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(out.with_name(out.stem+'-capture'+out.suffix)),full_page=False)
  page.goto(url+'&sector=dining&property=bhcs');page.wait_for_selector('.sector-metrics[data-sector=dining]');assert page.locator('#property-filter').input_value()=='bhcs'
  page.goto(url+'&platform=youxuan&property=youxuan');page.wait_for_selector('.commerce-metrics')
  assert all(x in page.locator('#workspace').inner_text() for x in ['森活优选','联营产品','电商带货','零售产品','支付成交GMV','平台已履约净收入'])
  assert all(x not in page.locator('#workspace').inner_text() for x in ['入住率','RevPAR','ADR'])
  assert page.locator('#property-filter option[value=spa]').inner_text()=='芳疗SPA'
  shop=client.get(url.split('?')[0]+'demo/report-youxuan-30.json?v=1.7.0').json()['commerce']['metrics']
  assert shop['paid_gmv']>shop['recognized_income'];assert f"{shop['paid_gmv']:,.0f}" in page.locator('.commerce-metrics .metric').first.inner_text()
  page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(out.with_name(out.stem+'-select'+out.suffix)),full_page=False)
  assert not errors,errors
  assert not failures,failures
  assert not any('/api/' in u for u in urls)
  print(json.dumps({'url':url,'public_site':'PASS','metrics':8,'order_drill':'PASS','collaboration_and_capture_entry':'PASS','professional_dining_and_water':'PASS','direct_sector_link':'PASS','senhuo_select':'PASS','spa_rename':'PASS','filters':'PASS','resource_errors':0,'script_errors':0,'backend_requests':0,'tls_verification':True,'screenshot':str(out)},ensure_ascii=False))
 finally:browser.close()
