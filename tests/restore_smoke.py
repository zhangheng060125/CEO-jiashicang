"""Snapshot, restore into a separate directory, start a fresh process and verify persistence.
No production database replacement and no secret values printed.
"""
import os,sys,sqlite3,subprocess,tempfile,socket,time,json
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import server
with tempfile.TemporaryDirectory(prefix='senhuo-restore-') as td:
 td=Path(td);backup=td/'backup.sqlite3';restored=td/'restored'
 subprocess.run([sys.executable,str(ROOT/'scripts/backup.py'),str(backup)],check=True,cwd=ROOT)
 with sqlite3.connect(backup) as c:
  baseline=c.execute('SELECT COUNT(*) FROM records').fetchone()[0]
  demo_count=c.execute("SELECT COUNT(*) FROM records WHERE dataset='demo' AND kind='order'").fetchone()[0]
 subprocess.run([sys.executable,str(ROOT/'scripts/restore.py'),str(backup),str(restored)],check=True,cwd=ROOT)
 with sqlite3.connect(restored/'hotel.sqlite3') as c:
  assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==baseline
  assert c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0
  assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 # A second attempt must refuse to overwrite the first restored database.
 denied=subprocess.run([sys.executable,str(ROOT/'scripts/restore.py'),str(backup),str(restored)],capture_output=True,text=True)
 assert denied.returncode!=0 and 'exists' in denied.stderr
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 runtime_env={**os.environ,'HOTEL_DATA_DIR':str(restored),'PORT':str(port),'HOTEL_ALLOW_DEMO':'1','HOTEL_SECURE_COOKIE':'0'}
 with open(td/'server.log','w') as log:
  proc=subprocess.Popen([sys.executable,str(ROOT/'server.py')],cwd=ROOT,env=runtime_env,stdout=log,stderr=log)
  try:
   client=httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=10)
   deadline=time.monotonic()+15
   while True:
    try:
     if client.get('/api/health').status_code==200:break
    except httpx.TransportError:pass
    if proc.poll() is not None or time.monotonic()>deadline:raise AssertionError('Restored server failed to become ready')
    time.sleep(.1)
   assert client.post('/api/login',json={'demo':True}).status_code==200
   assert len(client.get('/api/records/order?dataset=demo').json()['records'])==demo_count
   assert client.get('/api/dashboard?dataset=demo').status_code==200
   client.close()
   with sqlite3.connect(restored/'hotel.sqlite3') as c:assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==baseline
   print(json.dumps({'restore':'PASS','integrity':'ok','new_process':'ready','record_counts':'match','old_sessions':'revoked','overwrite':'refused'}))
  finally:
   proc.terminate()
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()
