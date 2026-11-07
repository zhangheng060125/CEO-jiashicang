"""Verify and restore a full bundle into a NEW directory, never overwrite business data."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

p=argparse.ArgumentParser(description=__doc__);p.add_argument('backup',type=Path);p.add_argument('destination',type=Path);args=p.parse_args()
if args.destination.exists():raise SystemExit('Destination exists; use a new directory')
args.destination.parent.mkdir(parents=True,exist_ok=True)
def copy_limited(source,target,limit):
 size=0
 with target.open('xb') as out:
  target.chmod(0o600)
  while chunk:=source.read(1024*1024):
   size+=len(chunk)
   if size>limit:raise ValueError('Archive entry exceeds declared limit')
   out.write(chunk)
 return size
with tempfile.TemporaryDirectory(prefix='senhuo-restore-',dir=args.destination.parent) as folder,zipfile.ZipFile(args.backup) as archive:
 folder=Path(folder);names=archive.namelist();entries=archive.infolist()
 if len(names)!=len(set(names)) or len(names)>20000 or sum(x.file_size for x in entries)>5*1024**3:raise SystemExit('Archive limits exceeded')
 if 'hotel.sqlite3' not in names:raise SystemExit('Database missing from bundle')
 db=folder/'source.sqlite3'
 with archive.open('hotel.sqlite3') as src:copy_limited(src,db,512*1024**2)
 with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as c:
  if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Database integrity check failed')
  media=c.execute('SELECT storage_name,sha256,size FROM work_media').fetchall() if c.execute("SELECT 1 FROM sqlite_master WHERE name='work_media'").fetchone() else []
 expected={'hotel.sqlite3'}|{'media/'+r[0] for r in media}
 if set(names)!=expected:raise SystemExit('Unexpected or missing archive entries')
 restored=folder/'runtime'
 subprocess.run([sys.executable,str(Path(__file__).resolve().with_name('restore.py')),str(db),str(restored)],check=True)
 directory=restored/'private_media';directory.mkdir(mode=0o700)
 for name,digest,size in media:
  if not re.fullmatch(r'[a-f0-9]{32}\.[a-z0-9]+',name) or size>64*1024**2:raise SystemExit('Unsafe attachment record')
  path=directory/name
  with archive.open('media/'+name) as src:
   if copy_limited(src,path,size)!=size:raise SystemExit('Attachment size mismatch')
  with path.open('rb') as src:
   if hashlib.file_digest(src,'sha256').hexdigest()!=digest:raise SystemExit('Attachment checksum mismatch')
 os.rename(restored,args.destination)
 print(f'Full restore verified: {len(media)} attachments; old sessions and connectors revoked; source untouched.')
