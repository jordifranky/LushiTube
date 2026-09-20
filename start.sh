#!/bin/sh
set -eu

echo "[LushiTube] Node: $(node --version)"
echo "[LushiTube] Python: $(python --version 2>&1)"
echo "[LushiTube] FFmpeg: $(ffmpeg -version 2>/dev/null | head -n 1)"
echo "[LushiTube] yt-dlp: $(python -m yt_dlp --version 2>/dev/null || true)"

echo "[LushiTube] Iniciando proveedor PO Token en 127.0.0.1:4416..."
node /opt/bgutil/server/build/main.js --host 127.0.0.1 --port 4416 >/tmp/pot-provider.log 2>&1 &
POT_PID=$!

cleanup() {
  kill "$POT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

POT_READY=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then
    POT_READY=1
    echo "[LushiTube] PO Token provider listo."
    break
  fi
  sleep 1
done

if [ "$POT_READY" -ne 1 ]; then
  echo "[LushiTube] AVISO: el proveedor PO Token no respondió. Últimas líneas:"
  tail -n 40 /tmp/pot-provider.log 2>/dev/null || true
fi

echo "[LushiTube] Iniciando Gunicorn en puerto ${PORT:-10000}..."
exec gunicorn app:app \
  --bind "0.0.0.0:${PORT:-10000}" \
  --workers 1 \
  --threads 4 \
  --timeout 1800 \
  --keep-alive 5 \
  --access-logfile - \
  --error-logfile -
