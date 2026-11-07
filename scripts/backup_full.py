"""Consistent database + immutable private attachments backup. Never reads initial passwords."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path);args=p.parse_args()
runtime=Path(os.environ.get('HOTEL_DATA_DIR',ROOT/'.runtime'));source=runtime/'hotel.sqlite3';target=args.destination
if not source.is_file():raise SystemExit('Source database missing')
if target.exists():raise SystemExit('Destination exists; choose a new backup filename')
target.parent.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='senhuo-backup-',dir=target.parent) as folder:
 folder=Path(folder);db=folder/'hotel.sqlite3';bundle=folder/'full.zip'
 with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as src:
  with sqlite3.connect(db) as dst:src.backup(dst)
 with sqlite3.connect(db) as c:
  if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Database integrity failed')
  media=c.execute('SELECT storage_name,sha256,size FROM work_media').fetchall() if c.execute("SELECT 1 FROM sqlite_master WHERE name='work_media'").fetchone() else []
 with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
  archive.write(db,'hotel.sqlite3')
  for name,expected,size in media:
   if not re.fullmatch(r'[a-f0-9]{32}\.[a-z0-9]+',name):raise SystemExit('Unsafe attachment name')
   path=runtime/'private_media'/name
   if path.is_symlink() or not path.is_file() or path.stat().st_size!=size:raise SystemExit('Attachment missing or changed; backup refused')
   with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
   if actual!=expected:raise SystemExit('Attachment checksum mismatch; backup refused')
   archive.write(path,'media/'+name)
 bundle.chmod(0o600);os.link(bundle,target)
 print(f'Full backup verified: database and {len(media)} private attachments; credentials file excluded.')
