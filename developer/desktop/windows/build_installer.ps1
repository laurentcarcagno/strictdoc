<#
.SYNOPSIS
  Build the Windows installer of the StrictDoc desktop application.

.DESCRIPTION
  Creates a virtual environment, installs StrictDoc with pywebview (without
  the "qt" extra: the window uses WebView2), builds the PyInstaller folder
  with its tools (headless Chrome, chromedriver, frozen html2pdf4doc, MinGit)
  and two programs: strictdoc.exe (console) and strictdoc-desktop.exe (no
  console window, the one the shortcut starts), then compiles strictdoc-desktop.iss with Inno Setup. The installer is for
  one user (no administrator rights).

  The signing step is present and off. It runs only with -SignCertificate.

.PARAMETER RepoPath
  The StrictDoc repository. Default: two folders above this script's folder.
.PARAMETER WorkDir
  Where the virtual environment, the build and the downloads go.
.PARAMETER OutputDir
  Where the installer goes.
.PARAMETER Python
  A Python 3.10 to 3.13 (pythonnet, needed by pywebview, has no wheel for
  the newest versions). Default: the py launcher with 3.12.
.PARAMETER InnoSetup
  Path of ISCC.exe. Default: the usual places of Inno Setup 6.
.PARAMETER SignCertificate
  A path to a .pfx file, or the thumbprint of a certificate of the store.
  Without it, nothing is signed. The password of a .pfx file is read from
  the variable STRICTDOC_SIGN_PASSWORD, never from the command line.
#>
param(
    [string]$RepoPath = (Resolve-Path "$PSScriptRoot\..\..\..").Path,
    [string]$WorkDir = "$PSScriptRoot\work",
    [string]$OutputDir = "$PSScriptRoot\dist",
    [string]$Python = "py -3.12",
    [string]$InnoSetup = "",
    [string]$SignCertificate = ""
)

$ErrorActionPreference = "Stop"
$Venv = Join-Path $WorkDir "venv"
$AppDir = Join-Path $WorkDir "application"
$PyInstallerDir = Join-Path $WorkDir "pyinstaller"
$DownloadCache = Join-Path $WorkDir "downloads"

function Invoke-Checked {
    param([string]$Command)
    Write-Host ">> $Command"
    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0) { throw "Failed ($LASTEXITCODE): $Command" }
}

function Find-InnoSetup {
    if ($InnoSetup -ne "") { return $InnoSetup }
    $Candidates = @(
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) { return $Candidate }
    }
    throw "ISCC.exe not found. Install Inno Setup 6 or pass -InnoSetup."
}

function Invoke-Signing {
    param([string]$File)
    # signtool.exe comes with the Windows SDK.
    if (Test-Path $SignCertificate) {
        if ([string]::IsNullOrEmpty($env:STRICTDOC_SIGN_PASSWORD)) {
            throw "Set STRICTDOC_SIGN_PASSWORD for a .pfx certificate."
        }
        & signtool.exe sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
            /f $SignCertificate /p $env:STRICTDOC_SIGN_PASSWORD $File
    }
    else {
        & signtool.exe sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
            /sha1 $SignCertificate $File
    }
    if ($LASTEXITCODE -ne 0) { throw "Signing failed ($LASTEXITCODE): $File" }
}

New-Item -ItemType Directory -Force -Path $WorkDir, $OutputDir | Out-Null

# 1. The virtual environment. The installation of StrictDoc brings its
#    dependencies; the build itself reads the sources of the repository (the
#    current folder of PyInstaller comes first in its search path).
if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    Invoke-Checked "$Python -m venv `"$Venv`""
}
$VenvPython = "$Venv\Scripts\python.exe"
Invoke-Checked "& `"$VenvPython`" -m pip install --upgrade pip"
Invoke-Checked "& `"$VenvPython`" -m pip install `"$RepoPath`" pywebview platformdirs keyring pyinstaller jaraco.text"

# 2. The folder of the application, with its tools. On win64, build_onedir.py
#    builds strictdoc.exe and strictdoc-desktop.exe in the same folder.
Invoke-Checked "& `"$VenvPython`" `"$RepoPath\developer\desktop\build_onedir.py`" --platform win64 --app-dir `"$AppDir`" --work-dir `"$PyInstallerDir`" --cache-dir `"$DownloadCache`""
if (-not (Test-Path (Join-Path $AppDir "strictdoc-desktop.exe"))) { throw "strictdoc-desktop.exe is missing in $AppDir" }

# 3. The version, read the way build_deb.py reads it.
$VersionLine = Select-String -Path "$RepoPath\strictdoc\__init__.py" -Pattern '^__version__ = "([^"]+)"'
if ($null -eq $VersionLine) { throw "No __version__ in strictdoc\__init__.py." }
$Version = $VersionLine.Matches[0].Groups[1].Value

# 4. The installer.
$Compiler = Find-InnoSetup
Invoke-Checked "& `"$Compiler`" /DAppVersion=$Version /DAppDir=`"$AppDir`" /DOutputDir=`"$OutputDir`" `"$PSScriptRoot\strictdoc-desktop.iss`""
$Installer = Join-Path $OutputDir "strictdoc-desktop-setup-$Version.exe"
if (-not (Test-Path $Installer)) { throw "The installer is missing: $Installer" }

# 5. The signature (off by default: Windows only serves tests, decision D-27).
if ($SignCertificate -ne "") {
    Invoke-Signing $Installer
    Write-Host "Signed: $Installer"
}
else {
    Write-Host "Not signed (no -SignCertificate)."
}

$SizeMb = [math]::Round((Get-Item $Installer).Length / 1MB)
Write-Host "Installer: $Installer ($SizeMb MB)"
