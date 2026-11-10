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
stay in a Docker volume between two runs, one volume per architecture
(strictdoc-tests-build-amd64, strictdoc-tests-build-arm64; docker volume rm
starts again from nothing). The test reports are copied to
build/docker/test_reports; the other outputs go away with the container.

The image is built for the architecture of the Docker engine (amd64 or
arm64), which the script asks Docker at each run: a change of machine
rebuilds the image for the new one instead of emulating the old one.

Behind a proxy that inspects TLS, put its root certificates (*.crt) in
developer/docker_tests/certs/ before the first run.
#>

$ErrorActionPreference = 'Stop'

$Image = 'strictdoc-tests:local'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Reports = Join-Path $Root 'build\docker'

$Command = $args
if ($Command.Count -eq 0) {
    $Command = @('invoke', 'test-unit')
}

# The architecture of the Docker engine: amd64 or arm64.
$Arch = (docker version --format '{{.Server.Arch}}').Trim()
if ($LASTEXITCODE -ne 0 -or $Arch -eq '') {
    throw 'Docker does not answer. Start Docker Desktop.'
}
$Platform = "linux/$Arch"
$Volume = "strictdoc-tests-build-$Arch"

# Docker Desktop on WSL 2 mounts the fixed drives of Windows, not the
# removable ones (a USB disk): the container would see an empty folder. The
# drive of the working tree is mounted in the WSL distribution of Docker
# Desktop when it is not there yet. The mount lasts until WSL restarts.
$DistroList = (wsl --list --quiet 2>$null) -join "`n" -replace "`0", ''
if ($DistroList -match '(?m)^docker-desktop\s*$') {
    $Drive = (Split-Path -Qualifier $Root).TrimEnd(':')
    $Letter = $Drive.ToLower()
    $Mount = "/mnt/host/$Letter"
    wsl -d docker-desktop -u root sh -c "mountpoint -q $Mount || { mkdir -p $Mount && mount -t drvfs ${Drive}: $Mount -o metadata,uid=0,gid=0; }"
    if ($LASTEXITCODE -ne 0) {
        throw "The drive ${Drive}: could not be mounted for Docker."
    }
}

# Quick when nothing changed: Docker reuses its cache.
docker build --quiet --platform $Platform --tag $Image $PSScriptRoot | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The image $Image could not be built for $Platform."
}

if (Test-Path (Join-Path $Reports 'test_reports')) {
    Remove-Item -Recurse -Force (Join-Path $Reports 'test_reports')
}
New-Item -ItemType Directory -Force $Reports | Out-Null

# --init: Chrome leaves child processes that something has to reap.
# --shm-size: Chrome needs more shared memory than the 64 MB by default.
docker run --rm --init --shm-size=2g --platform $Platform `
    --volume "${Root}:/src:ro" `
    --volume "${Volume}:/strictdoc/build/uv" `
    --volume "${Reports}:/out" `
    $Image @Command
exit $LASTEXITCODE
