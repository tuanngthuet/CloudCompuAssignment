FROM python:3.12-slim-bookworm
WORKDIR /srv/labseat
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=180000
COPY requirements.lock .
COPY tests/app/requirements-browser.lock /tmp/browser.lock
RUN pip install --no-cache-dir -r requirements.lock -r /tmp/browser.lock && pip check && python -m playwright install --with-deps chromium
COPY tests/app tests/app
RUN useradd --uid 10001 --create-home labseat
USER labseat
CMD ["python", "-m", "pytest", "tests/app/test_browser.py", "-v", "-p", "no:cacheprovider"]
