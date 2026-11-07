"""Full API-backed Select board, finance confirmation, inventory and phone layout."""
import json,os,subprocess,sys
from playwright.sync_api import sync_playwright
from runtime_support import isolated_server,ROOT

with isolated_server(HOTEL_ALLOW_DEMO='1') as (base,runtime),sync_playwright() as p:
    for script in ['seed_demo.py','seed_extensions.py','seed_workspace_demo.py','seed_sectors_demo.py','seed_commerce_demo.py']:
        subprocess.run([sys.executable,str(ROOT/script)],env={**os.environ,'HOTEL_DATA_DIR':str(runtime)},cwd=ROOT,check=True,capture_output=True)
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/?platform=youxuan&property=youxuan');page.locator('#demo-login').click();page.wait_for_selector('.commerce-metrics')
    assert '森活优选' in page.locator('#page-title').inner_text()
    assert all(word not in page.locator('#workspace').inner_text() for word in ['入住率','RevPAR','ADR'])
    assert all(word in page.locator('#workspace').inner_text() for word in ['自营产品','联营产品','电商带货','零售产品','支付成交GMV','平台已履约净收入','合作方待追偿'])
    assert page.locator('.commerce-metrics .metric').count()==8
    props=page.request.get(base+'/api/records/property?dataset=demo').json()['records'];assert next(x['data']['name'] for x in props if x['property_id']=='spa')=='芳疗SPA'
    report=page.request.get(base+'/api/dashboard?dataset=demo&property_id=youxuan').json()['commerce'];assert report['metrics']['paid_gmv']>report['metrics']['recognized_income']
    page.locator('#commerce-mode').select_option('affiliate');assert '联营产品' not in page.locator('#commerce-orders').inner_text()
    page.locator('[data-commerce-line]').first.click();page.wait_for_selector('#modal[open]');assert '电商带货' in page.locator('#modal-body').inner_text();page.locator('#modal .close').click()
    page.locator('[data-commerce-metric=recognized_income]').click();page.wait_for_selector('#modal[open]');assert '来源' in page.locator('#modal-body').inner_text() or '凭证' in page.locator('#modal-body').inner_text();page.locator('#modal .close').click()
    page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(ROOT/'docs/commerce-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(ROOT/'docs/commerce-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1050})
    page.locator('[data-commerce-new=commerce_product]').click();page.wait_for_selector('#record-form')
    for key,value in dict(code='DEMO-BROWSER-PRODUCT',name='演示·新增产品',unit='件',owner='浏览器产品负责人').items():page.locator('#record-form [name='+key+']').fill(value)
    page.locator('#record-form [name=mode]').select_option('affiliate');assert page.locator('#record-form [name=owned_stock]').input_value()=='false'
    page.locator('#record-form button[type=submit]').click();page.wait_for_function("!document.querySelector('#modal').open")
    rows=page.request.get(base+'/api/records/commerce_product?dataset=demo&property_id=youxuan').json()['records'];assert any(x['data']['code']=='DEMO-BROWSER-PRODUCT' for x in rows)
    page.locator('[data-commerce-open=commerce_line]').click();page.wait_for_selector('#export-records')
    with page.expect_download() as got:page.locator('#export-records').click()
    assert got.value.suggested_filename=='demo-commerce_line.csv'
    page.locator('[data-view=shop]').click();page.wait_for_selector('.commerce-metrics')
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#property-filter').select_option('spa');page.wait_for_selector('.sector-metrics[data-sector=spa]');assert '芳疗SPA' in page.locator('#page-title').inner_text()
    assert not errors,errors
    browser.close();print(json.dumps(dict(select_board='PASS',spa_rename='PASS',modes_and_net_income='PASS',event_drilldown='PASS',catalog_persistence='PASS',scoped_export='PASS',mobile='PASS')))
