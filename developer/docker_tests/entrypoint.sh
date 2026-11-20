#!/bin/sh
# Copies the working tree into the container, runs the command (an invoke
# task by default), then copies the test reports to /out.
set -eu

snapshot.py /src /strictdoc
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
