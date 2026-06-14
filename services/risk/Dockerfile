# Risk service image. Build context is the REPO ROOT (see docker-compose.yml) so the shared
# package is available: `from shared.schemas import ...`.
FROM python:3.11-slim

WORKDIR /app

# The risk service runs the forensic analyzer in-process, so it needs Tesseract for the
# §6.D2 re-OCR cross-check. Without it the check no-ops (scoring is unaffected).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY services/risk/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY services/ ./services/

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8002
CMD ["uvicorn", "services.risk.app.main:app", "--host", "0.0.0.0", "--port", "8002"]
