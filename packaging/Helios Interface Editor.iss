#define MyAppName "Helios Interface Editor"
#define MyAppExeName "Helios Interface Editor.exe"
#define MyAppVersion "1.0.0"

[Setup]
AppId={{9A3C818B-9FB7-4D0A-9F11-77A6DB01A2BB}
AppName={#MyAppName}
AppVerName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Elite
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayName={#MyAppName}
SetupIconFile=..\app\assets\Helios Interface Editor.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..
OutputBaseFilename=HeliosInterfaceEditorSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[InstallDelete]
Type: files; Name: "{autodesktop}\{#MyAppName}.lnk"

[Files]
Source: "..\app\assets\Helios Interface Editor.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\artifacts\dist\Helios Interface Editor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Helios Interface Editor.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\Helios Interface Editor.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent