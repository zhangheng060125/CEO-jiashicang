"""Verify trusted local TLS and proxy headers; does not claim Nginx/live-domain validation."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import ssl
import subprocess
from threading import Thread
import httpx
from runtime_support import isolated_server

with isolated_server(HOTEL_SECURE_COOKIE='1') as (backend, runtime):
    cert, key = runtime/'cert.pem', runtime/'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1',
                    '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *_):pass
        def forward(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ('connection', 'content-length')}
            headers['X-Forwarded-Proto'] = 'https'
            headers['X-Forwarded-For'] = '127.0.0.1'
            with httpx.Client(trust_env=False) as upstream:
                response = upstream.request(self.command, backend+self.path, content=body, headers=headers)
            self.send_response(response.status_code)
            for name, value in response.headers.multi_items():
                if name.lower() not in ('connection', 'content-length', 'transfer-encoding', 'content-encoding'):
                    self.send_header(name, value)
            self.send_header('Content-Length', str(len(response.content))); self.end_headers()
            self.wfile.write(response.content)
        do_GET = forward
        do_POST = forward
    proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls.load_cert_chain(cert, key)
    proxy.socket = tls.wrap_socket(proxy.socket, server_side=True)
    thread = Thread(target=proxy.serve_forever, daemon=True); thread.start()
    try:
        origin = 'https://localhost:'+str(proxy.server_port)
        trust = ssl.create_default_context(cafile=str(cert))
        with httpx.Client(base_url=origin, verify=trust, trust_env=False) as client:
            assert client.get('/api/health').status_code == 200
            assert client.post('/api/login', json={'demo': True}, headers={'Origin': origin}).status_code == 403
            password = (runtime/'admin-password.txt').read_text().split('password: ', 1)[1].strip()
            response = client.post('/api/login', json={'username': 'admin', 'password': password}, headers={'Origin': origin})
            assert response.status_code == 200, response.text
            assert 'secure' in response.headers['set-cookie'].lower() and 'httponly' in response.headers['set-cookie'].lower()
            assert client.get('/api/me').status_code == 200
            assert client.post('/api/logout', headers={'Origin': 'https://invalid.example'}).status_code == 403
            assert client.post('/api/logout', headers={'Origin': origin}).status_code == 200
            assert client.get('/api/me').status_code == 401
        print(json.dumps({'trusted_local_tls': 'PASS', 'secure_cookie': 'PASS', 'proxy_origin': 'PASS', 'public_demo_disabled': 'PASS'}))
    finally:
        proxy.shutdown(); proxy.server_close(); thread.join(timeout=5)
