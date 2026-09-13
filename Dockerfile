FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-chi-sim \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the frozen third-party dependency set before application sources so
# ordinary source changes retain this expensive Docker layer.
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir --upgrade 'setuptools>=84.0.0' \
    && pip install --no-cache-dir uv==0.11.17 \
    && uv export --frozen --no-dev --no-emit-project --format requirements-txt \
       | pip install --no-cache-dir -r /dev/stdin \
    && pip uninstall -y uv

# Both import roots must be present before the editable project install because
# setuptools discovers `app`, `agent_core`, and `llm_router` from these trees.
COPY packages/ ./packages/
COPY app/ ./app/
RUN pip install --no-cache-dir --no-deps -e .

# Migration assets (kept after the install so they don't bust the wheel cache)
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/

# Keep both the application and reusable agent kernel importable at runtime.
ENV PYTHONPATH=/app:/app/packages

# Expose port
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-4}"]
