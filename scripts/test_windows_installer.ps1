<#
Run on a disposable Windows CI runner. The script refuses to replace an existing
Gel Analyzer installation. It validates a current-user installation, reinstall,
optional simulated earlier-version upgrade, shortcuts, and uninstall.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [string]$Version = "1.0.3",
    [string]$PreviousInstaller,
    [string]$PreviousVersion = "1.0.2",
    [string]$Python = ".venv/Scripts/python.exe",
    [string]$OutputDirectory = "dist/windows/validation/installer"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Installer = (Resolve-Path $Installer).Path
if ($PreviousInstaller) { $PreviousInstaller = (Resolve-Path $PreviousInstaller).Path }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$installDirectory = Join-Path $env:LOCALAPPDATA "Programs\Gel Analyzer"
$executable = Join-Path $installDirectory "Gel Analyzer.exe"
$registryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\org.benpollak.gelanalyzer.windows_is1"
$startMenuDirectory = Join-Path ([Environment]::GetFolderPath("Programs")) "Gel Analyzer"
$startMenuShortcut = Join-Path $startMenuDirectory "Gel Analyzer.lnk"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("DesktopDirectory")) "Gel Analyzer.lnk"
$results = [ordered]@{
    started_at = [DateTime]::UtcNow.ToString("o")
    status = "running"
    installer = [IO.Path]::GetFileName($Installer)
    target_version = $Version
    checks = [Collections.Generic.List[string]]::new()
    limitations = @(
        "Installation runs on a provisioned CI image, not a clean physical Windows PC.",
        "When supplied, the previous-version installer is a simulated upgrade fixture."
    )
}
$installedByTest = $false

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Get-WebViewRuntimeFiles {
    $roots = @(
        (Join-Path $env:LOCALAPPDATA "Microsoft\EdgeWebView\Application"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft\EdgeWebView\Application"),
        (Join-Path $env:ProgramFiles "Microsoft\EdgeWebView\Application")
    )
    return @($roots | Where-Object { Test-Path $_ } | ForEach-Object {
        Get-ChildItem -LiteralPath $_ -Filter msedgewebview2.exe -Recurse -File |
            Select-Object -ExpandProperty FullName
    } | Sort-Object -Unique)
}

function Invoke-Setup([string]$Path, [string]$Name) {
    $log = Join-Path $OutputDirectory "$Name.log"
    $arguments = @("/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                   "/TASKS=desktopicon", "/LOG=`"$log`"")
    $process = Start-Process -FilePath $Path -ArgumentList $arguments -Wait -PassThru
    Assert-True ($process.ExitCode -eq 0) "$Name failed with installer exit code $($process.ExitCode); see $log"
}

function Assert-Installation([string]$ExpectedVersion) {
    Assert-True (Test-Path $executable) "Installed executable is missing: $executable"
    Assert-True (Test-Path $registryPath) "Per-user uninstall registration is missing"
    $registration = Get-ItemProperty -LiteralPath $registryPath
    Assert-True ($registration.DisplayVersion -eq $ExpectedVersion) "Installed version is $($registration.DisplayVersion), expected $ExpectedVersion"
    Assert-True ([IO.Path]::GetFullPath($registration.InstallLocation).TrimEnd("\") -eq $installDirectory) "Install location differs from the per-user default"
    Assert-True (Test-Path $startMenuShortcut) "Start menu shortcut is missing"
    Assert-True (Test-Path $desktopShortcut) "Selected desktop shortcut is missing"
    $shell = New-Object -ComObject WScript.Shell
    foreach ($path in @($startMenuShortcut, $desktopShortcut)) {
        $shortcut = $shell.CreateShortcut($path)
        Assert-True ($shortcut.TargetPath -eq $executable) "Shortcut target differs from installed app: $path"
    }
    Assert-True (@(Get-WebViewRuntimeFiles).Count -gt 0) "WebView2 runtime is not available after setup"
}

function Invoke-Uninstall {
    $uninstaller = @(Get-ChildItem -LiteralPath $installDirectory -Filter "unins*.exe" -File)
    Assert-True ($uninstaller.Count -eq 1) "Expected one registered uninstaller"
    $log = Join-Path $OutputDirectory "uninstall.log"
    $process = Start-Process -FilePath $uninstaller[0].FullName -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=`"$log`""
    ) -Wait -PassThru
    Assert-True ($process.ExitCode -eq 0) "Uninstaller exited with $($process.ExitCode)"
    # Inno's original uninstaller can exit before its temporary cleanup finishes.
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while ((Test-Path $executable) -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 200
    }
    Assert-True (-not (Test-Path $executable)) "App executable survived uninstall"
    Assert-True (-not (Test-Path $registryPath)) "Uninstall registration survived uninstall"
    Assert-True (-not (Test-Path $startMenuShortcut)) "Start menu shortcut survived uninstall"
    Assert-True (-not (Test-Path $desktopShortcut)) "Desktop shortcut survived uninstall"
}

try {
    Assert-True (-not (Test-Path $installDirectory)) "Refusing to replace an existing installation at $installDirectory"
    Assert-True (-not (Test-Path $registryPath)) "Refusing to replace an existing Gel Analyzer uninstall registration"
    Assert-True (-not (Test-Path $startMenuShortcut)) "Refusing to replace an existing Start menu shortcut"
    Assert-True (-not (Test-Path $desktopShortcut)) "Refusing to replace an existing desktop shortcut"
    if ($PreviousInstaller) {
        # Mark ownership before invoking setup so partial installations are cleaned.
        $installedByTest = $true
        Invoke-Setup $PreviousInstaller "install-previous-fixture"
        Assert-Installation $PreviousVersion
        $results.checks.Add("Simulated earlier-version installation ($PreviousVersion)")
    }
    $installedByTest = $true
    Invoke-Setup $Installer "install-current"
    Assert-Installation $Version
    $results.checks.Add("Default per-user installation and shortcut targets")
    if ($PreviousInstaller) {
        $results.checks.Add("Simulated earlier-version upgrade ($PreviousVersion to $Version)")
    } else {
        $results.limitations += "Earlier-version upgrade was not exercised because PreviousInstaller was omitted."
    }
    Invoke-Setup $Installer "reinstall-current"
    Assert-Installation $Version
    $results.checks.Add("Same-version reinstall")
    $smokeOutput = Join-Path $OutputDirectory "installed-smoke"
    & $Python (Join-Path $PSScriptRoot "smoke_windows.py") --exe $executable --output $smokeOutput
    Assert-True ($LASTEXITCODE -eq 0) "Installed app smoke tests failed; see $smokeOutput"
    $results.checks.Add("Installed app native-window, backend, browser, and export smoke checks")
    $runtimeBeforeUninstall = @(Get-WebViewRuntimeFiles)
    Invoke-Uninstall
    $installedByTest = $false
    foreach ($runtime in $runtimeBeforeUninstall) {
        Assert-True (Test-Path $runtime) "Uninstall removed shared WebView2 runtime: $runtime"
    }
    $results.checks.Add("Uninstall removes app, registration, and shortcuts")
    $results.checks.Add("Shared WebView2 runtime retained after uninstall")
    $results.status = "passed"
} catch {
    $results.status = "failed"
    $results.error = $_.ToString()
    throw
} finally {
    if ($installedByTest -and (Test-Path $installDirectory)) {
        try { Invoke-Uninstall } catch { $results.cleanup_error = $_.ToString() }
    }
    $results.finished_at = [DateTime]::UtcNow.ToString("o")
    $results | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $OutputDirectory "installer-results.json")
}
