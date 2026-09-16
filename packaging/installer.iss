#define AppName "D&D 5e Combat Simulator"
#define AppExeName "Dnd5eCombatSimulator.exe"

#ifndef AppVersion
  #error AppVersion must be supplied by the build script
#endif

[Setup]
SourceDir=..
AppId={{2C98AE07-3622-4B36-BBAC-9FD5A8385ED8}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\Dnd5eCombatSimulator
DefaultGroupName={#AppName}
OutputDir=dist\installer
OutputBaseFilename=Dnd5eCombatSimulator-Setup-{#AppVersion}
SetupIconFile=assets\app-icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
