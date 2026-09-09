# ============================================================
# Inventory Master OS - API (FastAPI)
# Imagen para despliegue en Oracle Cloud (Always Free) / Docker
# ============================================================
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Mexico_City

WORKDIR /app

# pg_dump/pg_restore para backups SQL y tzdata para programar el respaldo diario
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/app ./app

# Directorios que persisten en volúmenes Docker (backups y logos)
RUN mkdir -p /app/backups /app/uploads/logos \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# UN SOLO worker: evita duplicar el scheduler (APScheduler backups diarios) y
# los ratelimits en memoria cuando hay varios workers en un mismo contenedor.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]