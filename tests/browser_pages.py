"""Serve only static public assets under a repository subdirectory, like GitHub Pages."""
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread
import json
import shutil
import tempfile
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='senhuo-pages-test-') as folder,sync_playwright() as p:
 folder=Path(folder);site=folder/'CEO-jiashicang';site.mkdir()
 for name in ('index.html','app.js','preview.js','transport.js','style.css'):shutil.copyfile(ROOT/name,site/name)
 for name in ('demo','templates'):shutil.copytree(ROOT/name,site/name)
 class Quiet(SimpleHTTPRequestHandler):
  def log_message(self,*_):pass
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(folder)))
 thread=Thread(target=server.serve_forever,daemon=True);thread.start()
 base=f'http://127.0.0.1:{server.server_port}/CEO-jiashicang/'
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 try:
  page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];failures=[];requests=[]
  page.add_init_script('window.SENHUO_STATIC_PREVIEW=true;')
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('response',lambda r:failures.append((r.status,r.url)) if r.status>=400 and not r.url.endswith('favicon.ico') else None)
  page.on('request',lambda r:requests.append(r.url))
  page.goto(base);page.wait_for_selector('#preview-landing',state='visible');assert page.locator('#login-form').is_hidden()
  page.locator('#preview-enter').click();page.wait_for_selector('.metric');assert page.locator('.metric').count()==8
  assert '只读' in page.locator('#source-label').inner_text()
  manifest=json.loads((ROOT/'demo/manifest.json').read_text())
  expected=json.loads((ROOT/'demo'/manifest['reports']['all:30']).read_text())['metrics']['revenue']
  assert f'{expected:,.0f}' in page.locator('.metric').first.inner_text()
  page.reload();page.wait_for_selector('.metric')
  page.locator('#preview-guide').click();page.locator('[data-preview-step="1"]').click()
  page.locator('#preview-action').click();page.wait_for_selector('#modal[open]');assert '订单下钻' in page.locator('#modal').inner_text();page.locator('#modal .close').click()
  for key in ['inventory','channels','finance','operator','business','customers','issues','targets','data']:
   page.locator('[data-view="'+key+'"]').click();page.wait_for_function("!document.querySelector('#workspace').textContent.includes('正在读取')")
   assert '暂时无法加载' not in page.locator('#workspace').inner_text(),key
  page.locator('#static-kind').select_option('order');page.locator('#static-records').click();page.wait_for_selector('#export-records')
  assert page.locator('#new-record').is_disabled()
  with page.expect_download() as got:page.locator('#export-records').click()
  assert got.value.suggested_filename=='demo-order.csv'
  page.locator('[data-view="data"]').click();page.wait_for_selector('#static-template')
  with page.expect_download() as got:page.locator('#static-template').click()
  assert got.value.suggested_filename.endswith('.csv')
  page.locator('[data-view="issues"]').click();page.wait_for_selector('[data-alert]');page.locator('[data-alert]').first.click()
  page.wait_for_selector('#modal[open]');assert '只读' in page.locator('#modal').inner_text();assert page.locator('#record-form').count()==0;page.locator('#modal .close').click()
  result=page.evaluate("""async()=>{const m=await import('./transport.js?v=1.4.0');return [
   (await m.request('/api/dashboard?dataset=actual')).status,
   (await m.request('/api/records/customer',{method:'POST',body:'{}'})).status,
   (await m.request('/api/users')).status,
   (await m.request('/api/dashboard?dataset=demo&start=2020-01-01&end=2020-01-02')).status];}""")
  assert result==[403,403,403,422],result
  page.locator('[data-view="overview"]').click();page.wait_for_selector('.metric')
  page.locator('#property-filter').select_option('bhl');page.wait_for_selector('.metric')
  page.locator('#preview-period').select_option('7');page.wait_for_function("!document.querySelector('#workspace').textContent.includes('正在读取')")
  assert page.locator('#start-date').input_value()!=manifest['start']
  assert page.locator('#end-date').evaluate('(e)=>e.readOnly')
  page.locator('#preview-reset').click();page.wait_for_selector('.metric');page.wait_for_function("!document.querySelector('#preview-action').disabled")
  page.screenshot(path=str(ROOT/'docs/pages-desktop.png'),full_page=True)
  page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.screenshot(path=str(ROOT/'docs/pages-mobile.png'),full_page=True)
  page.locator('#preview-exit').click();page.wait_for_selector('#preview-landing',state='visible')
  page.locator('#preview-back').click();page.wait_for_selector('#modal[open]');assert page.locator('#login-form').is_hidden()
  assert not errors,errors
  assert not failures,failures
  assert not any('/api/' in url for url in requests),requests
  print(json.dumps({'pages_subdirectory':'PASS','all_modules':'PASS','order_drill':'PASS','period_and_property_filters':'PASS','downloads':'PASS','readonly_enforced':'PASS','no_backend_requests':True,'asset_errors':0,'mobile':'PASS'}))
 finally:
  browser.close();server.shutdown();server.server_close();thread.join(timeout=5)
