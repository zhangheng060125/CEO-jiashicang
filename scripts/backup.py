"""Consistent SQLite backup; run manually, never expose through the web server."""
import sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
if len(sys.argv)!=2:raise SystemExit('Usage: python scripts/backup.py /secure/path/backup.sqlite3')
target=Path(sys.argv[1])
if target.exists():raise SystemExit('Target exists; choose a new backup filename')
target.parent.mkdir(parents=True,exist_ok=True)
with server.db() as source:
 with sqlite3.connect(target) as destination:source.backup(destination)
target.chmod(0o600)
print('Database backup completed.')
