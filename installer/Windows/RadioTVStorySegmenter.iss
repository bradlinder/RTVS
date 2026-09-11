#define MyAppName "Radio & TV Segmenter"

#ifndef MyAppVersion
#define MyAppVersion "2.9.1"
#endif

#define MyAppPublisher "Radio & TV Segmenter"
#define MyAppURL "https://github.com/bradlinder/RTVS"
#define MyAppExeName "RadioTVSegmenter.exe"

[Setup]
AppId={{A9A4C9F1-0B2A-4C77-9F8C-111111111111}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Radio & TV Segmenter
UsePreviousAppDir=no
DirExistsWarning=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=RadioTVSegmenter-{#MyAppVersion}-Windows-Setup
SetupIconFile=..\..\resources\icon.ico
Compression=lzma2/fast
SolidCompression=yes
LZMAUseSeparateProcess=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
Uninstallable=yes
LicenseFile=..\..\NOTICES.txt
ChangesAssociations=yes

[InstallDelete]
; Clean up legacy shortcuts created by previous releases (with "Story" in the name)
Type: files; Name: "{autodesktop}\Radio & TV Story Segmenter.lnk"
Type: files; Name: "{group}\Radio & TV Story Segmenter.lnk"
; Clean up broken standalone worker binary from workers/ if left by older installer
Type: files; Name: "{app}\workers\prs_worker.exe"

[Files]
Source: "..\..\dist\RadioTVSegmenter\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\..\NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\icon.ico"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\icon.ico"
Name: "{group}\Third-Party Notices & Licenses"; Filename: "{app}\NOTICES.txt"

[Registry]
Root: HKA; Subkey: "Software\Classes\.rtvs"; ValueType: string; ValueName: ""; ValueData: "RTVSProject"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\RTVSProject"; ValueType: string; ValueName: ""; ValueData: "Radio & TV Segmenter Project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\RTVSProject\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\resources\icon.ico"
Root: HKA; Subkey: "Software\Classes\RTVSProject\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Never delete the per-user data directory. It contains projects, settings, logs,[cite: 10]
; downloaded models, and optional runtimes that should survive an application update/uninstall.[cite: 10]
Type: filesandordirs; Name: "{app}"
