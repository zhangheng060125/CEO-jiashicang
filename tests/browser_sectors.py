"""Restaurant, lodging, leisure and SPA screens, tailored forms and data-source handoff."""
from datetime import date,timedelta
import csv,json,os,subprocess,sys
from playwright.sync_api import sync_playwright
from runtime_support import isolated_server,ROOT

with isolated_server(HOTEL_ALLOW_DEMO='1') as (base,runtime),sync_playwright() as p:
    env={**os.environ,'HOTEL_DATA_DIR':str(runtime)}
    for script in ['seed_demo.py','seed_extensions.py','seed_workspace_demo.py','seed_sectors_demo.py']:
        subprocess.run([sys.executable,str(ROOT/script)],env=env,cwd=ROOT,check=True,capture_output=True)
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.locator('#demo-login').click();page.wait_for_selector('.metric')
    assert page.locator('.metric').count()==8
    assert page.locator('.sector-tile').count()==5
    page.locator('#property-filter').select_option('bhcs');page.wait_for_selector('.sector-metrics[data-sector=dining]')
    assert '餐饮经营' in page.locator('#page-title').inner_text()
    assert all(word not in page.locator('#workspace').inner_text() for word in ['入住率','RevPAR','ADR','未来7天预订'])
    assert page.locator('.metric').count()==8
    page.locator('[data-sector-metric=average_spend]').click();page.wait_for_selector('#modal[open]')
    assert '餐饮' in page.locator('#modal-body').inner_text();page.locator('#modal .close').click()
    page.locator('[data-view=inventory]').click();page.wait_for_selector('[data-sector-entry=dining]')
    assert page.locator('[data-view=business]').evaluate("e=>e.classList.contains('active')")
    page.locator('[data-sector-entry=dining]').click();page.wait_for_selector('#record-form')
    assert page.locator('#record-form [name=served_tables]').is_visible()
    assert page.locator('#record-form [name=visitors]').is_hidden()
    assert page.locator('#record-form [name=visitors]').is_disabled()
    tomorrow=(date.fromisoformat(page.request.get(base+'/api/health').json()['today'])+timedelta(days=1)).isoformat()
    for key,value in dict(day=tomorrow,available_tables='10',meal_periods='2',served_tables='18',labor_hours='16',owner='浏览器验收餐饮主管').items():page.locator('#record-form [name='+key+']').fill(value)
    page.locator('#record-form [name=complete]').select_option('true')
    page.locator('#record-form button[type=submit]').click();page.wait_for_function("!document.querySelector('#modal').open")
    rows=page.request.get(base+'/api/records/business_day?dataset=demo&property_id=bhcs').json()['records']
    assert len([r for r in rows if r['data']['day']==tomorrow and r['data']['business']=='dining'])==1
    with page.expect_download() as got:page.locator('[data-sector-template=dining]').click()
    header=next(csv.reader(open(got.value.path(),encoding='utf-8-sig')));assert 'served_tables' in header and 'visitors' not in header
    page.screenshot(path=str(ROOT/'docs/sector-dining.png'),full_page=True)
    page.locator('[data-view=overview]').click();page.wait_for_selector('.metric')
    page.locator('#property-filter').select_option('water');page.wait_for_selector('.sector-metrics[data-sector=water]')
    assert all(word not in page.locator('#workspace').inner_text() for word in ['入住率','RevPAR','ADR','间夜'])
    assert '入园' in page.locator('#workspace').inner_text() and '承载' in page.locator('#workspace').inner_text()
    page.screenshot(path=str(ROOT/'docs/sector-water.png'),full_page=True)
    page.locator('[data-view=wellness]').click();page.wait_for_selector('.sector-metrics[data-sector=spa]')
    page.locator('#property-filter').select_option('spa');page.wait_for_selector('[data-sector-entry=spa]')
    assert '同批预约完成率' in page.locator('#workspace').inner_text()
    page.locator('[data-sector-entry=spa]').click();page.wait_for_selector('#record-form')
    assert page.locator('[name=available_minutes]').is_visible();assert page.locator('[name=served_tables]').is_hidden();page.locator('#modal .close').click()
    page.locator('#property-filter').select_option('bhl');page.wait_for_selector('.metric')
    page.locator('[data-view=inventory]').click();page.wait_for_selector('.sector-metrics[data-sector=room]')
    assert '客房入住率' in page.locator('#workspace').inner_text();assert '食材耗用率' not in page.locator('#workspace').inner_text()
    page.screenshot(path=str(ROOT/'docs/sector-room.png'),full_page=True)
    page.locator('[data-view=retail]').click();page.wait_for_selector('.sector-metrics[data-sector=goods]');assert '会员与预售券权益余额' in page.locator('#workspace').inner_text()
    page.locator('[data-view=automation]').click();page.wait_for_selector('[download]')
    assert 'PMS' in page.locator('#workspace').inner_text() and 'POS' in page.locator('#workspace').inner_text()
    with page.expect_download() as got:page.locator('a[download]').click()
    assert got.value.suggested_filename=='data-sources.csv'
    page.locator('[data-view=overview]').click();page.wait_for_selector('.metric');page.locator('#property-filter').select_option('bhcs');page.wait_for_selector('.sector-metrics[data-sector=dining]')
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(ROOT/'docs/sector-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
    print(json.dumps(dict(sector_overviews='PASS',no_lodging_kpi_in_restaurants='PASS',scoped_drilldown='PASS',tailored_daily_forms='PASS',daily_persistence='PASS',compact_template='PASS',leisure_and_spa='PASS',automation_handoff='PASS',mobile='PASS')))
