# Forensics service image. Build context is the REPO ROOT (see docker-compose.yml) so the shared
# package is available: `from shared.schemas import ...`.
FROM python:3.11-slim

WORKDIR /app

# Tesseract OCR for entity extraction (Phase 2) + the re-OCR cross-check (§6.D2).
# If this layer is removed, OCR/re-OCR degrade gracefully (no crash, no re-OCR finding).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY services/forensics/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared contract and the services package. Compose also bind-mounts the repo at runtime
# for hot reload; this COPY keeps the image runnable on its own.
COPY shared/ ./shared/
COPY services/ ./services/

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8001
CMD ["uvicorn", "services.forensics.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
