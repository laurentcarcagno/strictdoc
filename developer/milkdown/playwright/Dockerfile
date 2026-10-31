# Playwright with Chromium, to check the diagram editor in a real browser.
# The base image has the architecture of the Docker host, so Chromium runs
# natively on arm64 as well as on x86-64 (the Chrome of the test image of the
# project has no arm64 build).
FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir playwright==1.49.1 \
    && playwright install --with-deps chromium
WORKDIR /work
