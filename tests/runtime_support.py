"""Isolated local process for acceptance checks; never selects the business DB."""
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def isolated_server(**settings):
    with tempfile.TemporaryDirectory(prefix='senhuo-acceptance-') as folder:
        runtime = Path(folder)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = {**os.environ, 'HOTEL_DATA_DIR': str(runtime), 'HOST': '127.0.0.1',
               'PORT': str(port), 'HOTEL_ALLOW_DEMO': '0', 'HOTEL_SECURE_COOKIE': '0', **settings}
        base = f'http://127.0.0.1:{port}'
        with (runtime/'server.log').open('w') as log:
            process = subprocess.Popen([sys.executable, str(ROOT/'server.py')], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                with httpx.Client(base_url=base, trust_env=False, timeout=2) as client:
                    deadline = time.monotonic()+20
                    while True:
                        try:
                            if client.get('/api/health').status_code == 200:break
                        except httpx.TransportError:pass
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise AssertionError('Isolated server did not become ready')
                        time.sleep(.1)
                yield base, runtime
            finally:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
