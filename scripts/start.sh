#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
if [[ -x .runtime/venv/bin/python ]]; then
  exec .runtime/venv/bin/python server.py
else
  exec python3 server.py
fi
