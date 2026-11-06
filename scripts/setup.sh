#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
python3 -m venv --system-site-packages .runtime/venv
.runtime/venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.runtime/venv/bin/python seed_demo.py
.runtime/venv/bin/python seed_extensions.py
.runtime/venv/bin/python scripts/generate_templates.py
.runtime/venv/bin/python -m unittest discover -s tests -v
node --check app.js
