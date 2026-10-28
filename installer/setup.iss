#define AppTitle "WuwaTappo全图鉴版"
[Setup]
AppId={{B0A64B37-C7C3-4E2F-925B-A4EBB90E92B2}
AppName={#AppTitle}
AppVersion=1.2
AppVerName={#AppTitle} 1.2
AppPublisher=Averionx
AppPublisherURL=https://github.com/Averionx/WuwaTappo-FullAtlas
AppSupportURL=https://github.com/Averionx/WuwaTappo-FullAtlas/issues
DefaultDirName={autopf}\WuwaTappoFullAtlas
DefaultGroupName={#AppTitle}
OutputDir=..\dist
OutputBaseFilename=WuwaTappo全图鉴版-1.2-Setup
Compression=lzma2/normal
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName={#AppTitle} 1.2
InfoBeforeFile=..\docs\INSTALL_NOTES.txt
SetupLogging=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\build\payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "host\*,cache\*,profile\*,local_config.json,offline_state.json,assistant_state.json,update_policy.json,.updates\*,*.log,client_diagnostics.jsonl"
Source: "..\build\payload\cache\*"; DestDir: "{app}\cache"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppTitle}"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\launch.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\WuwaTappo.Local.exe"
Name: "{autodesktop}\{#AppTitle}"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\launch.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\WuwaTappo.Local.exe"
Name: "{group}\恢复本地版联网"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\restore_network.ps1"""
Name: "{group}\使用说明"; Filename: "{app}\README.md"

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\initialize.ps1"""; Flags: runhidden waituntilterminated
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""{app}\launch.ps1"""; Description: "启动 {#AppTitle}"; Flags: postinstall nowait skipifsilent

[Code]
function InitializeUninstall(): Boolean;
var ResultCode: Integer;
begin
  Result := True;
  if FileExists(ExpandConstant('{app}\local_config.json')) then begin
    Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\restore_network.ps1') + '" -Cleanup',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Result := Result and (ResultCode = 0);
  end;
end;
