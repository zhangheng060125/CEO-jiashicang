"""Admin UI -> signed delivery -> scoped records -> revoke, in a disposable DB."""
import json
import sys
from runtime_support import isolated_server, ROOT
sys.path.insert(0, str(ROOT))
from scripts.adapter_push import signed_headers
from playwright.sync_api import sync_playwright

with isolated_server() as (base, runtime), sync_playwright() as p:
    password = (runtime/'admin-password.txt').read_text().split('password: ', 1)[1].strip()
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(base)
    page.locator('[name=username]').fill('admin'); page.locator('[name=password]').fill(password)
    page.locator('#login-form button[type=submit]').click(); page.wait_for_selector('.metric')
    page.locator('[data-view=data]').click(); page.locator('#integration-settings').click()
    page.locator('#new-connector').click()
    page.locator('#connector-form [name=name]').fill('浏览器接入验收')
    page.locator('#connector-form [name=properties]').select_option(['bhl'])
    page.locator('#connector-form [name=kinds]').select_option(['customer'])
    page.locator('#connector-form button').click(); page.wait_for_selector('#adapter-token')
    key = page.locator('#adapter-token').input_value()
    cid = page.locator('#created-connector-id').input_value()
    assert len(key) >= 40
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#connector-done').click(); page.wait_for_selector('#new-connector')
    assert key not in page.locator('body').inner_text()
    assert page.locator('#adapter-token').count() == 0
    raw = json.dumps({'batch_id': 'browser-1', 'dataset': 'actual', 'property_id': 'bhl', 'kind': 'customer',
                      'rows': [{'external_id': 'BROWSER-ADAPTER', 'code': 'BROWSER-ADAPTER', 'day': '2026-11-06', 'owner': '客服', 'status': 'new'}]}).encode()
    response = page.request.post(base+'/api/integrations/ingest', data=raw, headers=signed_headers(key, raw))
    assert response.status == 200 and response.json()['inserted'] == 1
    second = page.request.post(base+'/api/integrations/ingest', data=raw, headers=signed_headers(key, raw))
    assert second.json()['replayed']
    page.reload(); page.wait_for_selector('.metric')
    page.locator('[data-view=data]').click(); page.locator('#integration-settings').click()
    page.wait_for_selector('[data-revoke-connector]')
    assert 'browser-1' in page.locator('#modal-body').inner_text()
    assert len(page.request.get(base+'/api/records/customer?dataset=actual&property_id=bhl').json()['records']) == 1
    page.on('dialog', lambda d: d.accept())
    page.locator('[data-revoke-connector="'+cid+'"]').click()
    page.wait_for_function("document.querySelector('#modal-body').textContent.includes('已撤销')")
    assert page.request.post(base+'/api/integrations/ingest', data=raw, headers=signed_headers(key, raw)).status == 401
    assert not errors, errors
    browser.close()
    print(json.dumps({'browser_adapter': 'PASS', 'single_use_display': 'PASS', 'signed_delivery': 'PASS', 'duplicate': 'PASS', 'revocation': 'PASS', 'mobile': 'PASS'}))
