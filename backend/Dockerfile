FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app backend/app
COPY benchmarks/datasets benchmarks/datasets
COPY scripts scripts

# SQLite lives here; mount a persistent disk at /srv/data to keep history across restarts.
ENV ECOCOMPUTE_DATA_DIR=/srv/data ECOCOMPUTE_RESULTS_DIR=/srv/data/results
RUN useradd -m app && mkdir -p /srv/data && chown -R app /srv
USER app

WORKDIR /srv/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
