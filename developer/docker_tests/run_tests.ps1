<#
Runs the tests of StrictDoc in a Linux container (Docker Desktop) instead of
on Windows. The arguments are the command to run in the container, an invoke
task by default:

    powershell -File developer/docker_tests/run_tests.ps1
    powershell -File developer/docker_tests/run_tests.ps1 invoke test-unit-server
    powershell -File developer/docker_tests/run_tests.ps1 invoke test-integration --focus i18n
    powershell -File developer/docker_tests/run_tests.ps1 invoke test-end2end --headless

The container tests a copy of the working tree, uncommitted changes
included; the working tree itself is mounted read-only. The uv environments
stay in the Docker volume strictdoc-tests-build between two runs (docker
volume rm strictdoc-tests-build starts again from nothing). The test reports
are copied to build/docker/test_reports; the other outputs go away with the
container.

Behind a proxy that inspects TLS, put its root certificates (*.crt) in
developer/docker_tests/certs/ before the first run.
#>

$ErrorActionPreference = 'Stop'

$Image = 'strictdoc-tests:local'
$Volume = 'strictdoc-tests-build'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Reports = Join-Path $Root 'build\docker'

$Command = $args
if ($Command.Count -eq 0) {
    $Command = @('invoke', 'test-unit')
}

# Quick when nothing changed: Docker reuses its cache.
docker build --quiet --tag $Image $PSScriptRoot | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The image $Image could not be built."
}

if (Test-Path (Join-Path $Reports 'test_reports')) {
    Remove-Item -Recurse -Force (Join-Path $Reports 'test_reports')
}
New-Item -ItemType Directory -Force $Reports | Out-Null

# --init: Chrome leaves child processes that something has to reap.
# --shm-size: Chrome needs more shared memory than the 64 MB by default.
docker run --rm --init --shm-size=2g `
    --volume "${Root}:/src:ro" `
    --volume "${Volume}:/strictdoc/build/uv" `
    --volume "${Reports}:/out" `
    $Image @Command
exit $LASTEXITCODE
