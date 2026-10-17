#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(sys.version_info < (3,10))' >/dev/null 2>&1; then
  exec python3 scripts/app.py "$@"
elif command -v python >/dev/null 2>&1 && python -c 'import sys; sys.exit(sys.version_info < (3,10))' >/dev/null 2>&1; then
  exec python scripts/app.py "$@"
else
  echo 'Install Python 3.10+, Git and Docker with Compose v2, then retry.' >&2
  exit 1
fi
