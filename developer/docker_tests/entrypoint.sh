#!/bin/sh
# Copies the working tree into the container, runs the command (an invoke
# task by default), then copies the test reports to /out.
set -eu

snapshot.py /src /strictdoc

# An image with the Chromium of Debian (not amd64) has its own driver: the
# HTML2PDF tests and exports use it instead of downloading one.
if [ -x /usr/bin/chromedriver ]; then
    export CHROMEWEBDRIVER=/usr/bin
    export STRICTDOC_CHROMEDRIVER=/usr/bin/chromedriver
    # The end-to-end tests: SeleniumBase uses this driver instead of
    # downloading one for amd64 (see test_end2end in tasks.py).
    export STRICTDOC_SELENIUM_CHROMEDRIVER=/usr/bin/chromedriver
fi
# The reports of an earlier run are in the volume too.
rm -rf /strictdoc/build/test_reports

copy_reports() {
    if [ -d /out ] && [ -d /strictdoc/build/test_reports ]; then
        mkdir -p /out/test_reports
        cp -r /strictdoc/build/test_reports/. /out/test_reports/
    fi
}
trap copy_reports EXIT

"$@"
