ARG PYTHON_IMAGE=python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0
FROM ${PYTHON_IMAGE}
WORKDIR /srv/labseat
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY app app
COPY migrations migrations
RUN useradd --uid 10001 --create-home labseat && mkdir -p /data/images && chown labseat /data/images
USER labseat
ENV PORT=8000 LOCAL_STORAGE_PATH=/data/images PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
EXPOSE 8000
CMD ["python", "-m", "app.start"]
