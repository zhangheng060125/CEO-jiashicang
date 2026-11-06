"""Push a mapped JSON batch using the custom adapter protocol; no platform SDK.
Token comes from HOTEL_ADAPTER_TOKEN environment, never command arguments or logs.
"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx


def signed_headers(token, raw, timestamp=None, nonce=None):
    timestamp = str(timestamp if timestamp is not None else int(time.time()))
    nonce = nonce or secrets.token_urlsafe(24)
    message = timestamp.encode()+b'.'+nonce.encode()+b'.'+raw
    return {'Authorization': 'Bearer '+token, 'Content-Type': 'application/json',
            'X-Hotel-Timestamp': timestamp, 'X-Hotel-Nonce': nonce,
            'X-Hotel-Signature': hmac.new(token.encode(), message, hashlib.sha256).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    parser.add_argument('batch', type=Path)
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
        raise SystemExit('Use an HTTPS origin without credentials, path or query')
    token = os.environ.get('HOTEL_ADAPTER_TOKEN')
    if not token:
        raise SystemExit('HOTEL_ADAPTER_TOKEN is required')
    raw = args.batch.read_bytes()
    if len(raw) > 3*1024*1024 or not isinstance(json.loads(raw), dict):
        raise SystemExit('Batch must be a JSON object up to 3MB')
    try:
        response = httpx.post(args.base_url.rstrip('/')+'/api/integrations/ingest', content=raw,
                              headers=signed_headers(token, raw), timeout=60, follow_redirects=False)
    except httpx.HTTPError:
        raise SystemExit('Connection failed; check TLS, network and destination, then retry the same batch')
    if response.status_code != 200:
        raise SystemExit(f'Batch rejected (HTTP {response.status_code}); inspect the administrator integration log')
    result = response.json()
    print(json.dumps({k: result[k] for k in ('inserted', 'skipped', 'replayed')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
