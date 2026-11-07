"""Build public, read-only demo snapshots in a disposable DB; never export the runtime DB."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import date, timedelta

ROOT=Path(__file__).resolve().parents[1]


def worker(output):
 sys.path.insert(0,str(ROOT))
 import server as s
 import seed_demo,seed_extensions,seed_workspace_demo,seed_sectors_demo
 seed_demo.seed();seed_extensions.seed();seed_workspace_demo.seed();seed_sectors_demo.seed()
 with s.db() as c:rows=s.records(c,'demo')
 assert rows and all(r['dataset']=='demo' for r in rows)
 end=max(r['data']['day'] for r in rows if r['kind']=='fulfillment')
 props=[r['property_id'] for r in rows if r['kind']=='property']
 manifest={'version':'1.6.0','asof':end,'end':end,'generated_at':s.NOW(),
           'start':(date.fromisoformat(end)-timedelta(days=29)).isoformat(),
           'periods':[7,30],'properties':props,'record_count':len(rows),
           'source':'全新隔离库生成的模拟快照；未包含实际经营数据','reports':{}}
 output.mkdir(parents=True,exist_ok=True)
 def write(name,value):
  (output/name).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 write('records.json',rows);write('schema.json',s.SCHEMAS)
 # Export only newly generated demo collaboration samples, never the runtime media directory.
 media_dir=output/'media';media_dir.mkdir(exist_ok=True)
 import shutil
 with s.db() as c:
  actor={'username':'演示访客','role':'admin','properties':['*'],'demo':True}
  items=[]
  for row in c.execute("SELECT * FROM work_items WHERE dataset='demo' ORDER BY id DESC"):
   assert row['submitted_by']=='演示员工'
   value=s.WORKSPACE['pack'](c,actor,row);value['permissions']={'manage':False,'book':False,'direct':False}
   for position,media in enumerate(value['media']):
    stored=c.execute('SELECT storage_name FROM work_media WHERE id=?',(media['id'],)).fetchone()[0]
    public_name=f'sample-{row["id"]}-{position}.jpg'
    shutil.copyfile(s.DATA/'private_media'/stored,media_dir/public_name);media['url']='./demo/media/'+public_name
   items.append(value)
 write('workspace.json',{'items':items})
 for prop in ['',*props]:
  subset=rows if not prop else [r for r in rows if r['property_id']==prop]
  for days in manifest['periods']:
   start=(date.fromisoformat(end)-timedelta(days=days-1)).isoformat()
   report=s.metrics(subset,start,end,end)
   report['source']='只读演示快照 / 由服务端指标引擎计算；未连接真实平台'
   name=f'report-{prop or "all"}-{days}.json'
   write(name,report);manifest['reports'][f'{prop or "all"}:{days}']=name
 write('manifest.json',manifest)
 print(f'Built {len(rows)} synthetic records and {len(manifest["reports"])} scoped reports; actual DB untouched.')


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',type=Path,default=ROOT/'demo')
 p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
 args=p.parse_args()
 if args.worker:worker(args.output)
 else:
  with tempfile.TemporaryDirectory(prefix='senhuo-public-demo-') as folder:
   env={**os.environ,'HOTEL_DATA_DIR':folder}
   subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker','--output',str(args.output.resolve())],env=env,cwd=ROOT,check=True)
