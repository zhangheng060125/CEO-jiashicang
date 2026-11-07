"""Scheduled consistent backup; refuses a missing source and never removes backups."""
import os
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

if len(sys.argv) != 2 or not os.environ.get('HOTEL_DATA_DIR'):
    raise SystemExit('Set HOTEL_DATA_DIR and provide a backup directory')
source = Path(os.environ['HOTEL_DATA_DIR'])/'hotel.sqlite3'
if not source.is_file():
    raise SystemExit('Source database does not exist; backup refused')
destination = Path(sys.argv[1])
destination.mkdir(parents=True, exist_ok=True, mode=0o700)
target = destination/('hotel-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4)+'.sqlite3')
with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as check:
    has_media=check.execute("SELECT 1 FROM sqlite_master WHERE name='work_media'").fetchone() and check.execute('SELECT 1 FROM work_media LIMIT 1').fetchone()
if has_media:
    import subprocess
    subprocess.run([sys.executable,str(Path(__file__).resolve().with_name('backup_full.py')),str(target.with_suffix('.zip'))],check=True)
    raise SystemExit(0)
fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
os.close(fd)
try:
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro', uri=True) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed')
    print('Scheduled database backup completed and integrity verified.')
except Exception:
    target.unlink(missing_ok=True)
    raise
