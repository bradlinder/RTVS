#define MyAppName "Radio & TV Segmenter"
#define MyAppVersion "1.6.1"
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
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=RadioTVSegmenter-{#MyAppVersion}-Windows
SetupIconFile=..\..\resources\icon.ico
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMADictionarySize=65536
LZMANumBlockThreads=2
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
Uninstallable=yes
LicenseFile=..\..\NOTICES.txt

[Files]
Source: "..\..\dist\RadioTVSegmenter\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\icon.ico"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\icon.ico"
Name: "{group}\Third-Party Notices & Licenses"; Filename: "{app}\NOTICES.txt"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Never delete the per-user data directory. It contains projects, settings, logs,
; downloaded models, and optional runtimes that should survive an application update/uninstall.
Type: filesandordirs; Name: "{app}"
