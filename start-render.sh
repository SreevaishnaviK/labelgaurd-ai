#!/bin/bash
set -e

echo "Running database migrations..."
cd /app/backend
alembic upgrade head

echo "Starting Computer Vision..."
cd /app/computer-vision
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 &

echo "Starting AI service..."
cd /app/ai
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 &

echo "Starting Legal Engine..."
cd /app/legal-engine
python -m uvicorn app.main:app --host 127.0.0.1 --port 8003 &

echo "Starting Backend..."
cd /app/backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"