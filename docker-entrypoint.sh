#!/bin/sh
set -e

mkdir -p "${UPLOAD_DIR:-/app/uploads}"

if [ -f /certs/cert.pem ] && [ -f /certs/key.pem ]; then
    echo "[entrypoint] SSL certs found — starting with HTTPS"
    exec python -m uvicorn app.main:app \
        --host 0.0.0.0 --port 8000 \
        --ssl-certfile /certs/cert.pem \
        --ssl-keyfile /certs/key.pem
else
    echo "[entrypoint] No certs — starting with HTTP (behind nginx / reverse proxy)"
    exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
