#define MyAppName "Radio & TV Segmenter"
#define MyAppVersion "1.9.2"
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
ChangesAssociations=yes

[Files]
Source: "..\..\dist\RadioTVSegmenter\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

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
; Never delete the per-user data directory. It contains projects, settings, logs,
; downloaded models, and optional runtimes that should survive an application update/uninstall.
Type: filesandordirs; Name: "{app}"
