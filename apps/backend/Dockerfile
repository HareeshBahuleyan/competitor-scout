FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

# Local development image: imports resolve to the bind-synced /app/src so
# `docker compose watch` can sync source and restart without a rebuild.
FROM base AS dev

RUN pip install --no-cache-dir -e .

USER appuser

EXPOSE 8000
CMD ["uvicorn", "competitor_scout.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Default (last) stage: the deployed image, with the package installed as a copy.
FROM base AS runtime

USER appuser

EXPOSE 8000
CMD ["uvicorn", "competitor_scout.main:app", "--host", "0.0.0.0", "--port", "8000"]
