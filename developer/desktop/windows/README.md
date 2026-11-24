# Windows installer of the StrictDoc desktop application

The scripts of this folder were written on Linux and have not been run on
Windows. Expect to fix small things, and write them in the report below.

Windows only serves tests for now (decision D-27): the installer is not
signed. The signing step exists and stays off until a certificate is given.

## Prerequisites

- Windows 10 or 11 with the WebView2 runtime (installed with Edge).
- Python 3.10 to 3.13 (`py -3.12 --version`). pywebview needs pythonnet,
  which has no wheel for the newest Python versions.
- Inno Setup 6.3 or later (`ISCC.exe`).
- Access to the Internet, for pip and for the downloads of the tools
  (headless Chrome, chromedriver, MinGit). The script checks the SHA-256 sum
  of each file and stops on a wrong sum.
- The StrictDoc repository, on the branch of the desktop application.
- Git is not needed: the installer carries MinGit.

## Build

```powershell
powershell -File developer\desktop\windows\build_installer.ps1 `
  -RepoPath C:\dev\strictdoc `
  -WorkDir C:\dev\strictdoc-desktop-work
```

The installer is `dist\strictdoc-desktop-setup-<version>.exe` in the folder
of the script, or in `-OutputDir`. To sign it, add `-SignCertificate <path of
a .pfx file or thumbprint>`; the password of a `.pfx` file comes from the
variable `STRICTDOC_SIGN_PASSWORD`.

## Test scenario

Run it on a computer without Git and without Chrome, if you can.

1. Install: double-click the installer. No administrator prompt must
   appear. The menu has a "StrictDoc" shortcut, and the last page offers
   to start StrictDoc. Both start `strictdoc-desktop.exe`, which opens no
   console window. `strictdoc.exe` in the same folder is the command line
   program, with its console.
2. Start StrictDoc from the menu. The home screen opens in a window.
3. Open a project with a document (a copy of a project of the team).
4. Edit a node in the Markdown editor: type text, put a word in bold, insert
   a table of 3 columns and 2 rows. Save. Check in the `.sdoc` file that the
   bold word (`**bold**`) and the pipe table are there.
5. Merge: make a change of the same node on the remote (from another
   computer or a second copy), then synchronize. The merge window opens;
   keep the local text, finish the document.
6. Sign in with the account of the team.
7. Export a document to PDF. The PDF must come out without any Chrome
   installed on the computer and without a download (the files of the tools
   are in the `tools` folder of the installation).
8. Uninstall (Settings, Apps). The installation folder is gone. Your
   projects and settings are not touched.

## What to report

| Item | Result (OK / FAIL / difference) | Remark |
|---|---|---|
| Build of the installer | | error message if any |
| Size of the installer (MB) | | |
| Installation without administrator prompt | | |
| Shortcut in the menu | | |
| Window opens, home screen shows | | |
| Document opens | | |
| Editor: bold and table, saved in the `.sdoc` | | |
| Merge window (conflict, keep local, finish) | | |
| Sign-in | | |
| PDF export, no Chrome on the computer | | |
| No console window with the shortcut (`strictdoc-desktop.exe`) | | |
| Window opens with WebView2 (not Qt) | | |
| Uninstallation leaves nothing in the installation folder | | |
| Anything else | | |
