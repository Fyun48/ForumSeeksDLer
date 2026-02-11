; DLP01 Inno Setup 安裝腳本
;
; 使用方式:
;   1. 先執行 python build.py 產生 dist\DLP01 目錄
;   2. 使用 Inno Setup Compiler 編譯此腳本
;   3. 或執行 python build_installer.py 自動化整個流程

#define MyAppName "DLP01"
#define MyAppDisplayName "DLP01 - 論壇自動下載程式"
#define MyAppVersion "1.3.8"
#define MyAppPublisher "DLP01"
#define MyAppURL ""
#define MyAppExeName "DLP01.exe"

[Setup]
; 應用程式識別碼 (每個程式唯一)
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppDisplayName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 安裝目錄
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}

; 輸出設定
OutputDir=..\dist
OutputBaseFilename={#MyAppName}_Setup_v{#MyAppVersion}
; SetupIconFile=..\assets\icon.ico  ; 如有圖示檔案可取消註解
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; 權限設定
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 解除安裝設定
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppDisplayName}

; 其他設定
DisableProgramGroupPage=yes
LicenseFile=
InfoBeforeFile=
InfoAfterFile=

; 支援的語言
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; Name: "chinesetraditional"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"  ; 需另外下載

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; 主程式及所有檔案
Source: "..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 開始選單
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppDisplayName}}"; Filename: "{uninstallexe}"

; 桌面捷徑
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; 快速啟動
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; 安裝完成後詢問是否執行
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppDisplayName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; 可選: 註冊應用程式路徑
Root: HKCU; Subkey: "Software\{#MyAppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Code]
// 可選: 自訂安裝邏輯

// 安裝前檢查是否有舊版本正在執行
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;

  // 檢查程式是否正在執行
  if CheckForMutexes('{#MyAppName}_Mutex') then
  begin
    if MsgBox('{#MyAppDisplayName} 正在執行中。' + #13#10 + #13#10 +
              '請先關閉程式後再繼續安裝。', mbError, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := False;
    end;
  end;
end;

// 解除安裝前詢問是否保留設定
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    ConfigDir := ExpandConstant('{app}\config');
    if DirExists(ConfigDir) then
    begin
      if MsgBox('是否要保留設定檔？' + #13#10 + #13#10 +
                '選擇「是」保留設定，以便日後重新安裝時使用。' + #13#10 +
                '選擇「否」完全刪除所有檔案。',
                mbConfirmation, MB_YESNO) = IDNO then
      begin
        DelTree(ExpandConstant('{app}'), True, True, True);
      end;
    end;
  end;
end;
