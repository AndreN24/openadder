; Inno Setup script for OpenAdder (https://jrsoftware.org/isinfo.php).
; Build the app first (build.bat), then:  iscc /DMyAppVersion=1.0.0 installer\OpenAdder.iss
; The release workflow (.github/workflows/release.yml) does both steps automatically.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{6A0F2C1E-3B4D-4E8A-9C21-0DADDE0A0001}
AppName=OpenAdder
AppVersion={#MyAppVersion}
AppVerName=OpenAdder {#MyAppVersion}
AppPublisher=OpenAdder contributors
AppComments=Settings for the Razer DeathAdder V2 without Razer Synapse
DefaultDirName={localappdata}\Programs\OpenAdder
DefaultGroupName=OpenAdder
DisableProgramGroupPage=yes
; Per-user install: no administrator rights needed.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=OpenAdder-{#MyAppVersion}-Setup
SetupIconFile=..\assets\openadder.ico
UninstallDisplayIcon={app}\OpenAdder.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Ask the user to close a running OpenAdder before files are replaced or removed.
AppMutex=Local\OpenAdder
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "autostart"; Description: "Start OpenAdder with Windows (recommended, so your buttons always work)"; GroupDescription: "Start:"

[Files]
Source: "..\dist\OpenAdder\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\OpenAdder"; Filename: "{app}\OpenAdder.exe"
Name: "{group}\Uninstall OpenAdder"; Filename: "{uninstallexe}"
Name: "{userdesktop}\OpenAdder"; Filename: "{app}\OpenAdder.exe"; Tasks: desktopicon

[Registry]
; The same entry that the "Start with Windows" checkbox in OpenAdder uses.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "OpenAdder"; ValueData: """{app}\OpenAdder.exe"" --minimized"; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\OpenAdder.exe"; Description: "Start OpenAdder now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove the autostart entry also when it was turned on in the app, not in the installer.
Filename: "{cmd}"; Parameters: "/c reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v OpenAdder /f"; \
  Flags: runhidden; RunOnceId: "RemoveAutostart"
