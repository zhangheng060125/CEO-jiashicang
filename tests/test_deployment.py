import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from scripts.prepare_deployment import render

ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def test_configuration_validation_and_no_overwrite(self):
        files = render('hotel.example.com', '/opt/senhuo', '/var/lib/senhuo', '/var/backups/senhuo')
        self.assertIn('HOTEL_ALLOW_DEMO=0', files['production.env'])
        self.assertIn('HOTEL_SECURE_COOKIE=1', files['production.env'])
        self.assertIn('HOST=127.0.0.1', files['production.env'])
        self.assertNotIn('root ', files['senhuo.nginx.conf'])
        for domain in ('x;bad.com', 'x.com\nlocation /', '*.example.com'):
            with self.assertRaises(ValueError):render(domain, '/opt/senhuo', '/var/lib/senhuo', '/var/backups/senhuo')
        with self.assertRaises(ValueError):render('hotel.example.com', '/opt/senhuo', '/opt/senhuo/data', '/var/backups/senhuo')
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'review'
            command = [sys.executable, str(ROOT/'scripts/prepare_deployment.py'), '--domain', 'hotel.example.com', '--project', '/opt/senhuo', '--data', '/var/lib/senhuo', '--backups', '/var/backups/senhuo', '--output', str(target)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(len(list(target.iterdir())), 6)
            self.assertEqual((target/'production.env').stat().st_mode & 0o777, 0o600)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_scheduled_backup_and_restore_revoke_adapter(self):
        from test_system import s
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); source = tmp/'source'; source.mkdir()
            with s.db() as src:
                with sqlite3.connect(source/'hotel.sqlite3') as dest:
                    src.backup(dest)
                    dest.execute('INSERT INTO connectors(name,token_hash,dataset,properties,kinds,created_at,expires_at) VALUES(?,?,?,?,?,?,?)', ('restore-test', 'hash-only-test', 'actual', '["bhl"]', '["order"]', '2026', '2027'))
            command = [sys.executable, str(ROOT/'scripts/backup_daily.py'), str(tmp/'backups')]
            result = subprocess.run(command, env={**os.environ, 'HOTEL_DATA_DIR': str(source)}, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            backup = next((tmp/'backups').glob('*.sqlite3'))
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            restored = tmp/'restored'
            result = subprocess.run([sys.executable, str(ROOT/'scripts/restore.py'), str(backup), str(restored)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with sqlite3.connect(restored/'hotel.sqlite3') as c:
                self.assertEqual(c.execute('SELECT SUM(active) FROM connectors').fetchone()[0], 0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            with sqlite3.connect(source/'hotel.sqlite3') as c:
                self.assertEqual(c.execute("SELECT active FROM connectors WHERE name='restore-test'").fetchone()[0], 1)
            missing = subprocess.run(command, env={**os.environ, 'HOTEL_DATA_DIR': str(tmp/'missing')}, capture_output=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertEqual(len(list((tmp/'backups').glob('*.sqlite3'))), 1)
