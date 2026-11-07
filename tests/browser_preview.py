"""Exercise the guided preview in a disposable seeded DB, including real-session isolation."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from playwright.sync_api import sync_playwright
from runtime_support import isolated_server, ROOT


def actual_snapshot(runtime):
 with sqlite3.connect(runtime/'hotel.sqlite3') as c:
  rows=c.execute("SELECT * FROM records WHERE dataset='actual' ORDER BY id").fetchall()
 return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


with isolated_server(HOTEL_ALLOW_DEMO='1') as (base,runtime), sync_playwright() as p:
 env={**os.environ,'HOTEL_DATA_DIR':str(runtime)}
 for script in ('seed_demo.py','seed_extensions.py'):
  subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,env=env,check=True,capture_output=True)
 before=actual_snapshot(runtime)
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 password=(runtime/'admin-password.txt').read_text().split('password: ',1)[1].strip()
 page.goto(base);page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(password)
 page.locator('#login-form button[type=submit]').click();page.wait_for_selector('.metric')
 assert page.locator('#preview-toolbar').is_hidden()
 page.locator('#preview-link').click();page.wait_for_selector('#preview-landing',state='visible')
 assert not page.request.get(base+'/api/me').json()['demo']
 assert page.locator('#shell').is_hidden()
 page.screenshot(path=str(ROOT/'docs/preview-landing.png'),full_page=True)
 page.locator('#preview-enter').click();page.wait_for_selector('#preview-toolbar',state='visible')
 assert page.request.get(base+'/api/me').json()['demo']
 assert page.locator('#dataset').is_disabled() and page.locator('#dataset').input_value()=='demo'
 info=page.request.get(base+'/api/preview-info').json()
 assert page.locator('#end-date').input_value()==info['end']
 assert page.request.get(base+'/api/dashboard?dataset=actual').status==403
 assert page.request.post(base+'/api/records/customer',data={'dataset':'actual','property_id':'bhl','external_id':'ESCAPE','data':{'code':'ESCAPE','day':info['end'],'owner':'bad','status':'new'}}).status==403
 page.locator('#preview-guide').click();page.locator('[data-preview-step="1"]').click()
 page.wait_for_function("document.querySelector('#crumb').textContent.includes('订单')")
 page.locator('#preview-action').click();page.wait_for_selector('#modal[open]')
 assert '订单下钻' in page.locator('#modal').inner_text();page.locator('#modal .close').click()
 page.locator('#preview-next').click();page.wait_for_function("document.querySelector('#crumb').textContent.includes('未来房态')")
 assert '第 3 / 6 步' in page.locator('#preview-toolbar').inner_text()
 page.locator('#preview-next').click();page.wait_for_function("document.querySelector('#crumb').textContent.includes('全渠道')")
 page.locator('#preview-next').click();page.wait_for_function("document.querySelector('#crumb').textContent.includes('财务')")
 page.locator('#preview-next').click();page.wait_for_selector('[data-alert]')
 page.locator('[data-alert]').first.click();page.locator('[name=owner]').fill('预览验收负责人')
 page.locator('#record-form button[type=submit]').click();page.wait_for_function("!document.querySelector('#modal').open")
 issues=page.request.get(base+'/api/records/issue?dataset=demo').json()['records']
 assert any(r['data']['owner']=='预览验收负责人' for r in issues)
 page.locator('#preview-next').click();assert '导览已完成' in page.locator('#preview-toolbar').inner_text()
 page.reload();page.wait_for_selector('.metric');assert '导览已完成' in page.locator('#preview-toolbar').inner_text()
 page.locator('#property-filter').select_option('bhl');page.wait_for_selector('.metric')
 page.locator('#preview-reset').click();page.wait_for_function("document.querySelector('#property-filter').value==='' && document.querySelector('#preview-toolbar').textContent.includes('第 1 / 6 步')")
 assert any(r['data']['owner']=='预览验收负责人' for r in page.request.get(base+'/api/records/issue?dataset=demo').json()['records'])
 page.wait_for_selector('.metric');page.wait_for_function("!document.querySelector('#preview-action').disabled")
 page.screenshot(path=str(ROOT/'docs/preview-desktop.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.screenshot(path=str(ROOT/'docs/preview-mobile.png'),full_page=True)
 page.locator('#preview-guide').click();assert page.locator('[data-preview-step]').count()==6
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.locator('#modal .close').click()
 page.locator('#preview-exit').click();page.wait_for_selector('#preview-landing',state='visible')
 assert page.request.get(base+'/api/me').status==401
 page.locator('#preview-back').click();page.locator('[name=username]').fill('admin');page.locator('[name=password]').fill(password)
 page.locator('#login-form button[type=submit]').click();page.wait_for_selector('.metric')
 assert page.locator('#preview-toolbar').is_hidden() and page.locator('#dataset').input_value()=='actual'
 assert actual_snapshot(runtime)==before
 assert not errors,errors
 browser.close()
 print(json.dumps({'guided_preview':'PASS','six_steps':'PASS','order_drill':'PASS','issue_assignment':'PASS','restore_view_preserves_records':'PASS','actual_data_unchanged':'PASS','mobile':'PASS','exit_and_formal_login':'PASS'}))

with isolated_server(HOTEL_ALLOW_DEMO='0') as (base,runtime), sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 page=browser.new_page();page.goto(base+'/preview');page.wait_for_selector('#preview-landing',state='visible')
 assert page.locator('#preview-enter').is_disabled()
 assert '未开放体验' in page.locator('#preview-availability').inner_text()
 assert page.request.post(base+'/api/login',data={'demo':True}).status==403
 page.locator('#preview-back').click();assert page.locator('#login-demo').is_hidden()
 browser.close();print(json.dumps({'disabled_preview':'PASS'}))
