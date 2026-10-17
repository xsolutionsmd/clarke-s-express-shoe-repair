#!/bin/sh
set -eu
gunicorn --reload --config gunicorn.conf.py --bind 127.0.0.1:8081 wsgi:app &
backend=$!
trap 'kill "$backend" 2>/dev/null || true' EXIT INT TERM
npm ci --no-audit --no-fund
npm run dev
