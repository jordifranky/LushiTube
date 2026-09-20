#!/bin/sh
set -eu

echo "LushiTube: iniciando proveedor PO Token local..."
node /opt/bgutil/server/build/main.js --host 127.0.0.1 --port 4416 >/tmp/pot-provider.log 2>&1 &
POT_PID=$!

cleanup() { kill "$POT_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for i in 1 2 3 4 5; do
  if node -e "const n=require('net').connect(4416,'127.0.0.1');n.on('connect',()=>process.exit(0));n.on('error',()=>process.exit(1));"; then
    echo "LushiTube: proveedor PO Token listo."
    break
  fi
  sleep 1
done

echo "LushiTube: iniciando Gunicorn..."
exec gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 1800 --keep-alive 5 --access-logfile - --error-logfile -
