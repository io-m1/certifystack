FROM python:3.11-slim

WORKDIR /app

# System deps: tesseract for OCR, libgl for opencv
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    poppler-utils \
    libcairo2 \
    libpango-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    shared-mime-info \
    potrace \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads archive

EXPOSE 8080

# start.sh runs migrations at container startup (runtime), then launches gunicorn.
# Migrations must NOT run during build — the DB is unreachable then.
CMD ["sh", "start.sh"]
