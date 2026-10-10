FROM python:3.12-slim-bookworm

ARG APP_VERSION=dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    SMARTPLOY_APP_VERSION=${APP_VERSION}

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10002 smartploy \
    && useradd --system --uid 10002 --gid smartploy --home-dir /home/smartploy --create-home smartploy

WORKDIR /workspace
COPY . /workspace

RUN python -m pip install . \
    && chown -R smartploy:smartploy /workspace /home/smartploy

USER smartploy

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; r=urllib.request.Request('http://127.0.0.1:8090/healthz', headers={'Host':'smartploy.obumai.com'}); urllib.request.urlopen(r, timeout=4).read(256)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "smartploy.api:app", "--host", "0.0.0.0", "--port", "8090"]
