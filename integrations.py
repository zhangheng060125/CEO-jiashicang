"""Scoped custom-adapter ingestion. No native PMS/OTA connection is implied."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse


def install(s):
    with s.db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS connectors(
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
          dataset TEXT NOT NULL, properties TEXT NOT NULL, kinds TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS connector_nonces(
          connector_id INTEGER NOT NULL, nonce TEXT NOT NULL, seen_at INTEGER NOT NULL,
          PRIMARY KEY(connector_id,nonce));
        CREATE TABLE IF NOT EXISTS connector_batches(
          connector_id INTEGER NOT NULL, batch_id TEXT NOT NULL, body_hash TEXT NOT NULL,
          result TEXT NOT NULL, PRIMARY KEY(connector_id,batch_id));
        CREATE TABLE IF NOT EXISTS connector_events(
          id INTEGER PRIMARY KEY, connector_id INTEGER NOT NULL, at TEXT NOT NULL,
          batch_id TEXT, status INTEGER NOT NULL, detail TEXT NOT NULL);
        ''')

    def admin(request):
        u = s.auth(request)
        if u['role'] != 'admin' or u['demo']:
            s.err('仅真实集团管理员可管理接入凭证', 403)
        return u

    @s.app.get('/api/integrations')
    def listing(request: Request):
        admin(request)
        with s.db() as c:
            items = []
            for row in c.execute('SELECT id,name,dataset,properties,kinds,active,created_at,expires_at FROM connectors ORDER BY id DESC'):
                item = dict(row)
                item['properties'] = json.loads(item['properties'])
                item['kinds'] = json.loads(item['kinds'])
                item['expired'] = item['expires_at'] <= s.NOW()
                items.append(item)
            events = [dict(r) for r in c.execute('SELECT * FROM connector_events ORDER BY id DESC LIMIT 100')]
        return {'connectors': items, 'events': events, 'native_platform_connected': False}

    @s.app.post('/api/integrations')
    async def create(request: Request):
        u = admin(request)
        b = await s.read_json(request)
        name, dataset = b.get('name'), b.get('dataset')
        props, kinds, days = b.get('properties'), b.get('kinds'), b.get('expires_days', 90)
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            s.err('接入名称须为1至80字')
        s.scope(u, dataset)
        if not isinstance(props, list) or not props or not all(isinstance(p, str) and p != '*' for p in props):
            s.err('接入必须授权明确项目，不接受全域通配符')
        if not isinstance(kinds, list) or not kinds or not all(isinstance(k, str) and k in s.SCHEMAS and k != 'property' for k in kinds):
            s.err('选择有效业务数据类型；项目基础信息由管理员维护')
        if type(days) is not int or not 1 <= days <= 365:
            s.err('有效期必须为1至365天')
        with s.db() as c:
            known = {r['property_id'] for r in s.records(c, dataset, 'property')}
            if not set(props) <= known:
                s.err('授权项目不存在')
            token = secrets.token_urlsafe(32)
            expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            cid = c.execute('INSERT INTO connectors(name,token_hash,dataset,properties,kinds,created_at,expires_at) VALUES(?,?,?,?,?,?,?)',
                            (name.strip(), hashlib.sha256(token.encode()).hexdigest(), dataset,
                             json.dumps(sorted(set(props))), json.dumps(sorted(set(kinds))), s.NOW(), expires)).lastrowid
            s.audit(c, u, 'connector_create', None, dataset, '', {'connector_id': cid, 'properties': props, 'kinds': kinds, 'expires_at': expires})
        return {'id': cid, 'token': token, 'expires_at': expires, 'notice': '凭证仅展示一次，请交给授权适配程序保管；尚未连接任何平台'}

    @s.app.post('/api/integrations/{cid}/revoke')
    def revoke(cid: int, request: Request):
        u = admin(request)
        with s.db() as c:
            row = c.execute('SELECT dataset FROM connectors WHERE id=?', (cid,)).fetchone()
            if not row:
                s.err('接入不存在', 404)
            c.execute('UPDATE connectors SET active=0 WHERE id=?', (cid,))
            s.audit(c, u, 'connector_revoke', None, row['dataset'], '', {'connector_id': cid})
        return {'ok': True}

    @s.app.post('/api/integrations/ingest')
    async def ingest(request: Request):
        # Hash-only credentials, TLS in deployment, signed bytes and one-use nonce.
        authorization = request.headers.get('authorization', '')
        if not authorization.startswith('Bearer ') or len(authorization) > 200:
            s.err('接入凭证无效', 401)
        token = authorization[7:]
        digest = hashlib.sha256(token.encode()).hexdigest()
        with s.db() as c:
            row = c.execute('SELECT * FROM connectors WHERE token_hash=? AND active=1 AND expires_at>?', (digest, s.NOW())).fetchone()
        if not row:
            s.err('接入凭证无效或已过期', 401)
        timestamp = request.headers.get('x-hotel-timestamp', '')
        nonce = request.headers.get('x-hotel-nonce', '')
        signature = request.headers.get('x-hotel-signature', '')
        if not re.fullmatch(r'\d{10}', timestamp) or abs(time.time()-int(timestamp)) > 300:
            s.err('签名时间超过允许的5分钟窗口', 401)
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', nonce):
            s.err('nonce须为16至100位字母、数字、下划线或短横线', 401)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 3*1024*1024:
                s.err('接入批次不能超过3MB', 413)
        expected = hmac.new(token.encode(), timestamp.encode()+b'.'+nonce.encode()+b'.'+bytes(raw), hashlib.sha256).hexdigest()
        if not re.fullmatch(r'[a-f0-9]{64}', signature) or not hmac.compare_digest(expected, signature):
            s.err('签名校验失败', 401)
        status, result, batch_id = 200, None, ''
        with s.db() as c:
            # Serialize deduplication and revocation checks with the business write.
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM connectors WHERE id=? AND active=1 AND expires_at>?', (row['id'], s.NOW())).fetchone():
                s.err('接入已撤销或过期', 401)
            c.execute('DELETE FROM connector_nonces WHERE seen_at<?', (int(time.time())-610,))
            try:
                c.execute('INSERT INTO connector_nonces VALUES(?,?,?)', (row['id'], nonce, int(time.time())))
            except sqlite3.IntegrityError:
                s.err('重复签名请求，请使用新nonce重试同一批次', 409)
            c.execute('SAVEPOINT ingest_business')
            try:
                try:
                    body = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    s.err('接入内容必须是有效JSON对象', 400)
                if not isinstance(body, dict):
                    s.err('接入内容必须是JSON对象', 400)
                batch_id = body.get('batch_id')
                if not isinstance(batch_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', batch_id):
                    batch_id = ''
                    s.err('batch_id须为1至100位字母、数字、点、冒号、下划线或短横线')
                dataset, prop, kind, rows = (body.get(k) for k in ('dataset', 'property_id', 'kind', 'rows'))
                if dataset != row['dataset'] or prop not in json.loads(row['properties']) or kind not in json.loads(row['kinds']):
                    s.err('本接入未授权该数据集、项目或数据类型', 403)
                if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
                    s.err('每批须包含1至500行')
                permitted = set(s.SCHEMAS[kind]['fields']) | {'external_id'}
                if any(not isinstance(r, dict) or not set(r) <= permitted for r in rows):
                    s.err('行字段必须与模板一致，不接受未知字段')
                body_hash = hashlib.sha256(raw).hexdigest()
                prior = c.execute('SELECT * FROM connector_batches WHERE connector_id=? AND batch_id=?', (row['id'], batch_id)).fetchone()
                if prior:
                    if prior['body_hash'] != body_hash:
                        s.err('批次编号已使用且请求内容不同', 409)
                    result = {**json.loads(prior['result']), 'replayed': True}
                else:
                    actor = {'username': f'adapter:{row["id"]}', 'role': 'admin', 'properties': json.loads(row['properties']), 'demo': dataset == 'demo'}
                    result = {**s.import_rows(c, actor, kind, dataset, prop, rows), 'replayed': False}
                    c.execute('INSERT INTO connector_batches VALUES(?,?,?,?)', (row['id'], batch_id, body_hash, json.dumps(result)))
                    c.execute('INSERT INTO imports(at,actor,kind,dataset,property_id,filename,inserted,skipped,status,detail) VALUES(?,?,?,?,?,?,?,?,?,?)',
                              (s.NOW(), actor['username'], kind, dataset, prop, 'adapter:'+batch_id, result['inserted'], result['skipped'], 'success', '签名接入原子提交'))
                c.execute('RELEASE ingest_business')
            except HTTPException as ex:
                c.execute('ROLLBACK TO ingest_business')
                c.execute('RELEASE ingest_business')
                status, result = ex.status_code, {'detail': str(ex.detail)}
            c.execute('INSERT INTO connector_events(connector_id,at,batch_id,status,detail) VALUES(?,?,?,?,?)',
                      (row['id'], s.NOW(), batch_id, status, json.dumps(result, ensure_ascii=False)))
        return JSONResponse(result, status_code=status)
