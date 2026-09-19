#!/bin/bash
set -e

echo "Running database migrations..."
cd /app/backend
alembic upgrade head

echo "Starting Computer Vision..."
cd /app/computer-vision
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 > /tmp/cv.log 2>&1 &

echo "Waiting for Computer Vision..."

for i in {1..30}; do
    if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2)" >/dev/null 2>&1; then
        echo "Computer Vision is ready!"
        break
    fi

    if [ "$i" -eq 30 ]; then
        echo "Computer Vision failed to start."
        cat /tmp/cv.log
        exit 1
    fi

    sleep 1
done

echo "Starting AI service..."
cd /app/ai
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 > /tmp/ai.log 2>&1 &

echo "Starting Legal Engine..."
cd /app/legal-engine
python -m uvicorn app.main:app --host 127.0.0.1 --port 8003 > /tmp/legal.log 2>&1 &

echo "Starting Backend..."
cd /app/backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"