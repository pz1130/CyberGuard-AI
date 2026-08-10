FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-chi-sim \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The agent kernel lives in packages/ (agent_core, llm_router) and app/ imports
# it at module scope — app/services/run_event_log.py, tool_executor.py and the
# startup lifespan all do. Both trees must be present *before* `pip install -e .`
# or setuptools' packages.find (where = [".", "packages"]) resolves to nothing
# and the container dies on `ModuleNotFoundError: agent_core` at boot.
COPY pyproject.toml ./
COPY packages/ ./packages/
COPY app/ ./app/
RUN pip install --no-cache-dir -e .

# Migration assets (kept after the install so they don't bust the wheel cache)
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/

# Belt-and-braces: compose bind-mounts ./app and ./packages over the image
# contents for live reload, which bypasses the editable-install finder.
ENV PYTHONPATH=/app:/app/packages

# Expose port
EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-4}
