; Compile through scripts/build_windows.py. A previous AppVersion may also be
; supplied to make a clearly identified upgrade-test fixture from this bundle.
#ifndef AppVersion
  #error AppVersion must be supplied
#endif
#ifndef AppDir
  #error AppDir must point at the validated PyInstaller application directory
#endif
#ifndef OutputDir
  #error OutputDir must be supplied
#endif
#ifndef WebView2Installer
  #error WebView2Installer must point at the verified offline x64 installer
#endif

[Setup]
AppId=org.benpollak.gelanalyzer.windows
AppName=Gel Analyzer
AppVersion={#AppVersion}
AppPublisher=Gel Analyzer contributors
AppPublisherURL=https://github.com/BRPollak/gel-analyzer
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Gel Analyzer
DefaultGroupName=Gel Analyzer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible and not arm64
ArchitecturesInstallIn64BitMode=x64compatible and not arm64
MinVersion=10.0.19045
OutputDir={#OutputDir}
OutputBaseFilename=Gel-Analyzer-{#AppVersion}-Windows-x64-Setup
SetupIconFile=GelAnalyzer.ico
UninstallDisplayIcon={app}\Gel Analyzer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ChangesAssociations=no
Uninstallable=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; Extracted only when needed; the shared WebView2 runtime is never uninstalled.
Source: "{#WebView2Installer}"; DestName: "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Flags: dontcopy
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; This folder contains only our frozen dependencies. Remove obsolete libraries
; on upgrades, after Inno Setup has handled files in use.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{userprograms}\Gel Analyzer\Gel Analyzer"; Filename: "{app}\Gel Analyzer.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\Gel Analyzer"; Filename: "{app}\Gel Analyzer.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Gel Analyzer.exe"; Description: "Open Gel Analyzer"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2Key = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasRuntimeVersion(RootKey: Integer): Boolean;
var
  Version: String;
  PackedVersion: Int64;
begin
  Result := RegQueryStringValue(RootKey, WebView2Key, 'pv', Version);
  if Result then
    Result := StrToVersion(Version, PackedVersion) and
      (ComparePackedVersion(PackedVersion, PackVersionComponents(86, 0, 622, 0)) >= 0);
end;

function HasWebView2: Boolean;
begin
  { Microsoft's documented registry locations: per-user and 32-bit HKLM view. }
  Result := HasRuntimeVersion(HKCU) or HasRuntimeVersion(HKLM32);
end;

function InitializeSetup: Boolean;
begin
  Result := IsDotNetInstalled(net48, 0);
  if not Result then
    SuppressibleMsgBox(
      'Gel Analyzer requires .NET Framework 4.8, which is included with Windows 10 22H2 and Windows 11.' +
      #13#10#13#10 +
      'This Windows component is missing or unavailable. Ask your administrator to repair or enable it, then run Setup again.',
      mbCriticalError, MB_OK, IDOK);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  RuntimeInstaller: String;
begin
  Result := '';
  if HasWebView2 then
    exit;
  ExtractTemporaryFile('MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
  RuntimeInstaller := ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
  Log('Installing the bundled offline Microsoft Edge WebView2 Runtime for this user.');
  if not Exec(RuntimeInstaller, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
    Result := 'The bundled Microsoft Edge WebView2 Runtime installer could not start. ' +
      'Windows error: ' + IntToStr(ResultCode) + '.';
    exit;
  end;
  Log('WebView2 installer exit code: ' + IntToStr(ResultCode));
  if not HasWebView2 then begin
    if ResultCode = 3010 then
      NeedsRestart := True;
    Result := 'Microsoft Edge WebView2 Runtime could not be installed for this user (exit code ' +
      IntToStr(ResultCode) + '). Setup cannot continue. ' +
      'A Windows policy may be preventing installation; contact your administrator if this persists.';
  end;
end;
