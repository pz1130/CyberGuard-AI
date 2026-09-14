FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

WORKDIR /app

# Runner deps only (kept minimal; add security tools below as needed).
COPY tool-runner/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --upgrade 'setuptools>=84.0.0' \
    && pip install --no-cache-dir -r requirements.lock

# --- Security tools layer (extend this list as your team needs) ---
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        nmap \
    && rm -rf /var/lib/apt/lists/*

COPY tool_runner/ ./tool_runner/

ENV PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid 10001 cyberguard \
    && useradd --uid 10001 --gid 10001 --no-create-home \
        --shell /usr/sbin/nologin cyberguard

USER 10001:10001

EXPOSE 9000
CMD ["uvicorn", "tool_runner.main:app", "--host", "0.0.0.0", "--port", "9000"]
