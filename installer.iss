; Sunthemes — per-user установщик (Inno Setup 6), без прав администратора.
; Compile:  ISCC.exe installer.iss              (версия по умолчанию ниже)
;           ISCC.exe /DAppVersion=1.2.0 installer.iss   (версия из CI)
; Output:   dist\installer\SunthemesSetup.exe

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#define AppName "Sunthemes"
#define AppExe "Sunthemes.exe"
#define AppPublisher "Small-coder-AI"

[Setup]
; AppId фиксирован навсегда — по нему обновление находит прежнюю установку.
AppId={{8F2A6D14-4B7C-4E51-9C3A-2E5B7A1F6D90}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=SunthemesSetup
SetupIconFile=src\sunthemes\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "{code:StartupCaption}"; GroupDescription: "{code:StartupGroup}"

[Files]
Source: "dist\Sunthemes\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
; Пути совпадают с winapi.start_menu_shortcut_path() / desktop_shortcut_path() —
; приложение при первом запуске лишь обновит те же файлы, дубля не будет.
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Автозапуск в трей. Имя значения ThemeSwitcher — не менять (совместимость).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "ThemeSwitcher"; \
    ValueData: """{app}\{#AppExe}"" --tray"; \
    Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[Code]
function StartupCaption(Param: string): string;
begin
  if ActiveLanguage = 'ru' then Result := 'Запускать при старте Windows'
  else Result := 'Start with Windows';
end;

function StartupGroup(Param: string): string;
begin
  if ActiveLanguage = 'ru' then Result := 'Автозапуск:'
  else Result := 'Autostart:';
end;
