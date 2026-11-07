import json
from pathlib import Path
import unittest
from datetime import date,timedelta

ROOT=Path(__file__).resolve().parents[1]


class StaticDemoTests(unittest.TestCase):
 def test_public_records_are_synthetic_and_every_reference_is_in_demo(self):
  records=json.loads((ROOT/'demo/records.json').read_text())
  self.assertTrue(records)
  self.assertTrue(all(r['dataset']=='demo' for r in records))
  orders={(r['property_id'],r['data']['order_no']) for r in records if r['kind']=='order'}
  self.assertTrue(all(no.startswith('DEMO-') for prop,no in orders))
  for r in records:
   if r['kind']!='order' and r['data'].get('order_no'):self.assertIn((r['property_id'],r['data']['order_no']),orders)

 def test_reports_have_matching_scope_dates_and_order_totals(self):
  manifest=json.loads((ROOT/'demo/manifest.json').read_text())
  self.assertEqual(manifest['periods'],[7,30])
  for key,name in manifest['reports'].items():
   prop,days=key.rsplit(':',1);days=int(days)
   report=json.loads((ROOT/'demo'/name).read_text())
   self.assertEqual(len(report['daily']),days)
   self.assertEqual(report['daily'][-1]['day'],manifest['end'])
   self.assertEqual(report['daily'][0]['day'],(date.fromisoformat(manifest['end'])-timedelta(days=days-1)).isoformat())
   if prop!='all':self.assertTrue(all(r['property_id']==prop for r in report['orders']))
   revenue=report['metrics']['revenue']
   if revenue is not None:
    self.assertAlmostEqual(sum(r['fulfilled_revenue'] for r in report['orders']),revenue,places=2)
    self.assertAlmostEqual(sum(r['revenue'] or 0 for r in report['daily']),revenue,places=2)
