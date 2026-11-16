# Hugging Face Docker Space image (PRO plan) / local Gradio demo.
# Build context: repository root. Postgres + pgvector are provided by the
# `pgserver` pip wheel and started inside the container by app.py.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend \
    STORAGE_BACKEND=postgres \
    METRICS_BACKEND=postgres \
    EMBEDDED_POSTGRES=true \
    PGDATA=/data/pgdata \
    PORT=7860 \
    HOME=/home/appuser

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
COPY gradio_app/requirements.txt ./gradio_app/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r gradio_app/requirements.txt

COPY backend/reposage ./backend/reposage
COPY gradio_app/app.py ./app.py

# Spaces run the container as UID 1000.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 7860

CMD ["python", "/app/app.py"]
