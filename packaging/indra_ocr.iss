; Inno Setup script for the Indra OCR desktop app.
;
;   python packaging/build.py --console 0 --installer
;
; builds dist/IndraOCR/ with PyInstaller, then calls this script to wrap it in
; dist/IndraOCR-<version>-setup.exe.  A per-user install (no admin prompt) with a
; Start menu shortcut, an uninstall entry, and an optional .pdf association that
; starts the app on the double-clicked file.

#define AppName "Indra OCR"
#define AppExe "IndraOCR.exe"
#define AppId "{{7C3B1C1E-9A2F-4F0B-9E5A-2E5C7B6D1A44}"

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\IndraOCR"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Indra OCR
AppPublisherURL=https://github.com/datalab-to/indra
DefaultDirName={autopf}\IndraOCR
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist
OutputBaseFilename=IndraOCR-{#AppVersion}-setup
SetupIconFile=indra_ocr.ico
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
VersionInfoVersion={#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; A per-user install under %LOCALAPPDATA%\Programs: no admin, no UAC prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associatepdf"; Description: "Open .pdf files with {#AppName}"; GroupDescription: "File associations:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "IndraOCR.pdf"; ValueData: ""; Flags: uninsdeletevalue uninsdeletekeyifempty; Tasks: associatepdf
Root: HKCU; Subkey: "Software\Classes\IndraOCR.pdf"; ValueType: string; ValueName: ""; ValueData: "PDF document"; Flags: uninsdeletekey; Tasks: associatepdf
Root: HKCU; Subkey: "Software\Classes\IndraOCR.pdf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: associatepdf
Root: HKCU; Subkey: "Software\Classes\IndraOCR.pdf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: associatepdf

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The app writes nothing outside this folder except its state file, here.
Type: filesandordirs; Name: "{localappdata}\IndraOCR"
