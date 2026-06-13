# Risk service image. Build context is the REPO ROOT (see docker-compose.yml) so the shared
# package is available: `from shared.schemas import ...`.
FROM python:3.11-slim

WORKDIR /app

COPY services/risk/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY services/ ./services/

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8002
CMD ["uvicorn", "services.risk.app.main:app", "--host", "0.0.0.0", "--port", "8002"]
