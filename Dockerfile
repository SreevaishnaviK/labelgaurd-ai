FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY computer-vision/requirements.txt /tmp/cv-requirements.txt
COPY ai/requirements.txt /tmp/ai-requirements.txt
COPY legal-engine/requirements.txt /tmp/legal-requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    -r /tmp/backend-requirements.txt \
    -r /tmp/cv-requirements.txt \
    -r /tmp/ai-requirements.txt \
    -r /tmp/legal-requirements.txt
COPY backend /app/backend
COPY computer-vision /app/computer-vision
COPY ai /app/ai
COPY legal-engine /app/legal-engine

COPY start-render.sh /app/start-render.sh
RUN chmod +x /app/start-render.sh

RUN mkdir -p /data/uploads

EXPOSE 8000

CMD ["/app/start-render.sh"]