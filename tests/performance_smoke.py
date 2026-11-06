"""Bounded read-only baseline at the existing demo scale, not a capacity test."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import statistics
import time
import httpx

base = os.environ.get('HOTEL_TEST_URL', 'http://127.0.0.1:3001')
with httpx.Client(base_url=base, trust_env=False, timeout=30) as client:
    assert client.post('/api/login', json={'demo': True}).status_code == 200
    schema = client.get('/api/schema').json()
    record_count = sum(len(client.get('/api/records/'+kind+'?dataset=demo').json()['records']) for kind in schema['schemas'])
    start = time.perf_counter()
    baseline = client.get('/api/dashboard?dataset=demo')
    cold = time.perf_counter()-start
    assert baseline.status_code == 200
    expected = baseline.json()['metrics']
    def request(_):
        start = time.perf_counter()
        response = client.get('/api/dashboard?dataset=demo')
        elapsed = time.perf_counter()-start
        assert response.status_code == 200
        assert response.json()['metrics'] == expected
        return elapsed
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        elapsed = list(pool.map(request, range(24)))
    total = time.perf_counter()-started
    print(json.dumps({'dataset': 'demo', 'records': record_count, 'concurrency': 4, 'requests': len(elapsed),
                      'errors': 0, 'consistent_metrics': True, 'single_seconds': round(cold, 3),
                      'median_seconds': round(statistics.median(elapsed), 3),
                      'p95_seconds': round(sorted(elapsed)[math.ceil(.95*len(elapsed))-1], 3),
                      'total_seconds': round(total, 3), 'scope': 'current demo scale only'}, ensure_ascii=False))
