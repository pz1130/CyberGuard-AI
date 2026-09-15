FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

WORKDIR /app

# No pip install: this service uses the standard library only. The one process
# with internet access is the one that should carry the least code.
COPY egress_proxy/ ./egress_proxy/

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 cyberguard \
    && useradd --uid 10001 --gid 10001 --no-create-home \
        --shell /usr/sbin/nologin cyberguard

USER 10001:10001

EXPOSE 3128 3129
CMD ["python", "-m", "egress_proxy.main"]
