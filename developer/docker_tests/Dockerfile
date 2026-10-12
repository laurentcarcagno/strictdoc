# The image that runs the tests of StrictDoc in a Linux container.
# run_tests.ps1 builds it and runs it; see that script for the usage.
# The Python of .python-version.
FROM python:3.10-slim-bookworm

# A proxy that inspects TLS needs its root certificates here: put them in
# certs/ (*.crt, not committed). With no certificate, nothing changes.
COPY certs/ /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    UV_NATIVE_TLS=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    NO_PROXY=localhost,127.0.0.1,::1 \
    no_proxy=localhost,127.0.0.1,::1

# git: integration tests make repositories. libtidy: the HTML validator of
# the integration tests. gcc, g++: the gcov coverage tests. Chrome:
# end-to-end and HTML2PDF tests.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl g++ gcc git libtidy5deb1 \
    && curl -fsSL -o /tmp/chrome.deb \
       https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm -rf /tmp/chrome.deb /var/lib/apt/lists/*

# The tools of requirements.bootstrap.txt; uv installs the rest.
RUN pip install --no-cache-dir invoke toml uv

# Git settings at the system level: lit runs the tests without $HOME. The
# working tree mounted at /src belongs to another user than the tests.
RUN git config --system user.name "StrictDoc tests" \
    && git config --system user.email "tests@localhost" \
    && git config --system --add safe.directory '*'

# Chrome refuses to run as root without --no-sandbox: tests run as a user.
# The copy of the working tree goes to /strictdoc: some tests expect the
# name of the repository in the paths of their output. build/uv (the uv
# environments and the uv cache) is a volume, kept between two runs; the
# image gives it to that user. The rest of build/ stays on the same file
# system as the copy: Git stops looking for the repository at a mount point.
RUN useradd --create-home --uid 1000 tester \
    && mkdir -p /strictdoc/build/uv \
    && chown -R tester:tester /strictdoc
COPY --chmod=755 snapshot.py entrypoint.sh /usr/local/bin/
USER tester
ENV UV_CACHE_DIR=/strictdoc/build/uv/cache
WORKDIR /strictdoc

ENTRYPOINT ["entrypoint.sh"]
CMD ["invoke", "test-unit"]
