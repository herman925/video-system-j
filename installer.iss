; ============================================================
;  JAV Video System  —  Inno Setup installer script
;  Compile:  iscc installer.iss
;  Output:   setup\JAV Video System Setup.exe
; ============================================================

#define AppName       "JAV Video System"
#define AppVersion    "1.0.0"
#define AppPublisher  "KeySteps"
#define AppExeName    "JAV Video System.exe"
#define AppURL        "http://localhost:8765"
#define BuildDir      "dist\JAV Video System"

[Setup]
AppId                     = {{A3F8C2D1-7B44-4E9A-B6F3-2D1C8E5A9F0B}
AppName                   = {#AppName}
AppVersion                = {#AppVersion}
AppPublisher              = {#AppPublisher}
AppPublisherURL           = {#AppURL}
AppSupportURL             = {#AppURL}
AppUpdatesURL             = {#AppURL}

; Per-user install — no UAC prompt, installs to
; %LOCALAPPDATA%\Programs\JAV Video System (no admin required)
DefaultDirName            = {localappdata}\Programs\{#AppName}
DefaultGroupName          = {#AppName}
PrivilegesRequired        = lowest
PrivilegesRequiredOverridesAllowed = dialog

; Output
OutputDir                 = setup
OutputBaseFilename        = JAV Video System Setup
Compression               = lzma2/ultra64
SolidCompression          = yes
LZMAUseSeparateProcess    = yes

; Appearance
WizardStyle               = modern
WizardResizable           = yes
DisableWelcomePage        = no
DisableProgramGroupPage   = yes

; Uninstaller
UninstallDisplayName      = {#AppName}
UninstallDisplayIcon      = {app}\{#AppExeName}

; Versioning / upgrade — silently replaces previous install
CloseApplications         = yes
CloseApplicationsFilter   = *{#AppExeName}*
RestartApplications       = no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Desktop shortcut is opt-in
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Everything PyInstaller built (recursive)
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Explicitly exclude dev/temp artefacts that must never ship
; (PyInstaller normally won't include these, but belt-and-suspenders)
; Source: "{#BuildDir}\.env";        — never exists in dist, but excluded pattern-wise
; Source: "{#BuildDir}\config.json"; — same

[Icons]
; Start Menu
Name: "{group}\{#AppName}";          Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; Desktop (only if task selected)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch app after install
Filename: "{app}\{#AppExeName}"; \
  Description: "Launch {#AppName}"; \
  Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
; Kill the app before uninstalling
Filename: "taskkill.exe"; Parameters: "/f /im ""{#AppExeName}"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "KillApp"

[Code]
// Warn the user that app data (config, queue, API keys) lives in
// %APPDATA%\JAV Video System and will NOT be removed by the uninstaller.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    MsgBox(
      'Your settings, API keys and download queue are stored separately in:'
      + #13#10 + '%APPDATA%\JAV Video System'
      + #13#10#13#10
      + 'Existing data in %APPDATA%\JAV Downloader is also preserved for compatibility.'
      + #13#10
      + 'These folders will NOT be deleted. Remove them manually if you want a clean uninstall.',
      mbInformation, MB_OK
    );
  end;
end;
