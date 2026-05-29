FROM python:3.11-slim

WORKDIR /app

# Runner deps only (kept minimal; add security tools below as needed).
RUN pip install --no-cache-dir fastapi "uvicorn[standard]"

# --- Security tools layer (extend this list as your team needs) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        nmap \
    && rm -rf /var/lib/apt/lists/*

COPY tool_runner/ ./tool_runner/

EXPOSE 9000
CMD ["uvicorn", "tool_runner.main:app", "--host", "0.0.0.0", "--port", "9000"]
