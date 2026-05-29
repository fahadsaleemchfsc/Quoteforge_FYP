# QuoteForge backend — Render-ready image.
#
# Layered so dependency installs cache across code edits. python:3.11-slim
# rather than 3.12 because lightgbm/shap wheels are most reliable here.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgomp1 is required at runtime by lightgbm; build-essential is dropped
# after the pip install so we don't ship a compiler in the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Render sets $PORT; default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

# Healthcheck hits /healthz — defined in main.py and intentionally cheap
# (no DB call) so Render's probes don't compete with real traffic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:${PORT}/healthz || exit 1

# Single worker — the in-process APScheduler workers (CRM sync, insights
# retrain) assume one process. Scale horizontally only after they move out
# of the web dyno.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
