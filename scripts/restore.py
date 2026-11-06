"""Offline restore to a NEW runtime directory, with integrity verification and session revocation.
Never overwrites existing data. Stop the app before selecting the restored directory.
"""
import argparse,sqlite3,os
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('backup',type=Path);parser.add_argument('destination',type=Path);args=parser.parse_args()
if not args.backup.is_file():raise SystemExit('Backup not found')
args.destination.mkdir(parents=True,exist_ok=True,mode=0o700)
target=args.destination/'hotel.sqlite3'
if target.exists():raise SystemExit('Destination database exists; restore into a new directory')
source=sqlite3.connect(args.backup.resolve().as_uri()+'?mode=ro',uri=True)
try:
 if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Backup integrity check failed')
 required={'records','users','sessions','audit','imports','login_attempts'}
 if not required<={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}:raise SystemExit('Not a compatible hotel database')
 with sqlite3.connect(target) as restored:
  source.backup(restored);restored.execute('DELETE FROM sessions');restored.execute('DELETE FROM login_attempts')
  if restored.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='connectors'").fetchone():
   restored.execute('UPDATE connectors SET active=0');restored.execute('DELETE FROM connector_nonces')
  restored.commit()
  if restored.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Restored database integrity check failed')
 target.chmod(0o600)
 print('Restored to new directory; original database untouched; sessions revoked.')
finally:source.close()
