; Inno Setup script of the StrictDoc desktop application.
; Compiled by build_installer.ps1, which passes AppVersion, AppDir and
; OutputDir with /D.

#ifndef AppVersion
  #error AppVersion is not defined. Use build_installer.ps1.
#endif
#ifndef AppDir
  #error AppDir is not defined. Use build_installer.ps1.
#endif
#ifndef OutputDir
  #define OutputDir "dist"
#endif

[Setup]
; Never change the AppId: it links an installation to its uninstaller.
AppId={{6F0B8E5B-5D5E-4B3C-9C5A-2D6E7B1A4F10}
AppName=StrictDoc
AppVersion={#AppVersion}
AppPublisher=StrictDoc
DefaultDirName={autopf}\StrictDoc
DefaultGroupName=StrictDoc
DisableProgramGroupPage=yes
; Installation for one user: no administrator rights, no UAC prompt.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=strictdoc-desktop-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=StrictDoc
UninstallDisplayIcon={app}\strictdoc-desktop.exe
WizardStyle=modern

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; strictdoc-desktop.exe has no console window and runs "strictdoc desktop".
; strictdoc.exe keeps its console, for the command line.
Name: "{autoprograms}\StrictDoc"; Filename: "{app}\strictdoc-desktop.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\strictdoc-desktop.exe"; Description: "{cm:LaunchProgram,StrictDoc}"; Flags: nowait postinstall skipifsilent
