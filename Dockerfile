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

EXPOSE 8000
ENTRYPOINT ["/docker-entrypoint.sh"]
