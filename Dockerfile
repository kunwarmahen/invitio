FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV PYTHONPATH=/app/backend
# Uploaded images persist here; mount a volume at /app/uploads on the NAS.
ENV UPLOAD_DIR=/app/uploads

# Cache-busting build id (git sha + timestamp from deploy.sh). Baked in at build
# time so it's stable across container restarts; the app stamps it into each
# page's ?v= query, which invalidates the versioned css/js on every deploy.
ARG BUILD_VERSION=""
ENV BUILD_VERSION=$BUILD_VERSION

EXPOSE 8000
ENTRYPOINT ["/docker-entrypoint.sh"]
