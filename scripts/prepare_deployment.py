"""Render reviewable Linux/systemd + Nginx configuration; never activates services."""
import argparse
import os
from pathlib import Path
import re


def absolute_path(value):
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', value) or '..' in Path(value).parts or value == '/':
        raise argparse.ArgumentTypeError('Use an absolute path without spaces, shell symbols or ..')
    return value.rstrip('/')


def render(domain, project, data, backups, user='senhuo', port=3001):
    if len(domain) > 253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain):
        raise ValueError('Specify a valid lowercase DNS domain')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', user) or user == 'root':
        raise ValueError('Specify a non-root service user')
    for value in (project, data, backups):
        absolute_path(value)
    if not 1024 <= port <= 65535:
        raise ValueError('Port must be 1024..65535')
    if len({project, data, backups}) != 3 or any(Path(p).is_relative_to(project) for p in (data, backups)):
        raise ValueError('Keep data and backups outside the source directory')
    python = project+'/.venv/bin/python'
    hardening = f'''User={user}
Group={user}
WorkingDirectory={project}
EnvironmentFile={data}/production.env
Environment=PYTHONDONTWRITEBYTECODE=1
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={data} {backups}
'''
    return {
        'production.env': f'HOST=127.0.0.1\nPORT={port}\nHOTEL_DATA_DIR={data}\nHOTEL_SECURE_COOKIE=1\nHOTEL_ALLOW_DEMO=0\n',
        'senhuo.service': f'''[Unit]
Description=Senhuo CEO dashboard
After=network.target

[Service]
{hardening}Type=simple
ExecStart={python} {project}/server.py
Restart=on-failure
RestartSec=3
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
''',
        'senhuo-backup.service': f'''[Unit]
Description=Senhuo consistent database backup

[Service]
{hardening}Type=oneshot
ExecStart={python} {project}/scripts/backup_daily.py {backups}
''',
        'senhuo-backup.timer': '''[Unit]
Description=Daily Senhuo database backup

[Timer]
OnCalendar=*-*-* 03:15:00 Asia/Shanghai
Persistent=true
RandomizedDelaySec=5m
Unit=senhuo-backup.service

[Install]
WantedBy=timers.target
''',
        'senhuo.nginx.conf': f'''# Include in the Nginx http context. Obtain certificates before nginx -t.
server {{
    listen 80;
    server_name {domain};
    return 301 https://{domain}$request_uri;
}}
server {{
    listen 443 ssl;
    server_name {domain};
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 8m;
    add_header Strict-Transport-Security "max-age=31536000" always;
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 5s;
        proxy_read_timeout 90s;
        proxy_redirect off;
    }}
}}
''',
        'INSTALL.md': f'''# 待部署配置（尚未安装或启动）

域名：{domain}；代码：{project}；数据：{data}；备份：{backups}；服务用户：{user}。

1. 在目标 Linux 服务器安装 Python 3.12、venv、Nginx，创建专用用户/同名组 `{user}`。下载源码到上述代码目录；运行 `bash scripts/setup.sh` 安装并测试。另建生产虚拟环境：`python3 -m venv {project}/.venv`，再运行 `{project}/.venv/bin/python -m pip install -r {project}/requirements.txt`。生产服务使用 `.venv`，无需读取开发环境私有的 `.runtime`。生产环境由 `HOTEL_DATA_DIR` 指向独立目录，安装时的演示库不会自动成为真实经营库。
2. 创建数据与备份目录，归服务用户所有、权限700；源码归部署用户所有且服务用户可读/执行。复制 production.env 到 `{data}/production.env`，权限600且服务用户可读。若需接续已有业务，先按 docs/deployment.md 恢复备份到全新数据目录再使用该路径，勿覆盖现有数据库。
3. 将域名解析到服务器，取得有效TLS证书；若证书路径不同，修改 Nginx 配置中的两个 ssl 路径。仅对外开放80/443；应用绑定127.0.0.1。
4. 将三个 senhuo*.service/timer 文件放到 /etc/systemd/system/，执行 `systemd-analyze verify /etc/systemd/system/senhuo.service /etc/systemd/system/senhuo-backup.service /etc/systemd/system/senhuo-backup.timer`。将 Nginx 配置纳入现有 http 配置并执行 `nginx -t`。验证通过后再 daemon-reload、启动 senhuo.service 并重载 Nginx；按需要 enable 服务和备份 timer。
5. 通过HTTPS检查 /api/health、登录、实际数据导入/下钻、会话Secure标记、公开演示登录已禁用。首次管理员凭据在数据目录内，仅在服务器读取，登录后修改密码。
6. 手动运行一次 senhuo-backup.service，检查 journalctl 和生成文件，再验证恢复到新目录。确认后启用 senhuo-backup.timer。备份自动创建但不自动删除；按实际留存政策清理并配置异机副本/磁盘容量监控。

生成器只写配置，不安装软件、不更改系统服务、不申请证书、不发布公网。正式域名、证书和服务器的最终验证须在选定目标后完成。
'''
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--domain', required=True)
    p.add_argument('--project', required=True, type=absolute_path)
    p.add_argument('--data', required=True, type=absolute_path)
    p.add_argument('--backups', required=True, type=absolute_path)
    p.add_argument('--user', default='senhuo')
    p.add_argument('--port', type=int, default=3001)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    try:
        files = render(args.domain, args.project, args.data, args.backups, args.user, args.port)
    except ValueError as e:
        p.error(str(e))
    if args.output.exists():
        p.error('Output already exists; choose a new review directory')
    args.output.mkdir(parents=True, mode=0o700)
    for name, content in files.items():
        target = args.output/name
        target.write_text(content, encoding='utf-8')
        target.chmod(0o600)
    print('Generated 6 configuration files for review; no services changed.')


if __name__ == '__main__':
    main()
