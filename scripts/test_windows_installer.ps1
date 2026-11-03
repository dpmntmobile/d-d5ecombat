# Run only on a disposable GitHub Actions Windows runner: this changes machine
# installer registration and installs/uninstalls the application.
param(
    [string]$Python = ".venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
if ($env:GITHUB_ACTIONS -ne "true" -or -not $env:RUNNER_TEMP) {
    throw "Installer lifecycle checks require a disposable GitHub Actions runner."
}

$ProjectDirectory = Split-Path -Parent $PSScriptRoot
$TestRoot = Join-Path $env:RUNNER_TEMP ("combat-installer-" + [guid]::NewGuid())
$InstallDirectory = Join-Path $TestRoot "installed application"
$RegistryPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{2C98AE07-3622-4B36-BBAC-9FD5A8385ED8}_is1"
if (Test-Path -LiteralPath $RegistryPath) {
    throw "An existing application installation prevents a clean lifecycle test."
}
New-Item -ItemType Directory -Path $TestRoot | Out-Null

function Invoke-CheckedProcess([string]$File, [string[]]$Arguments, [int]$TimeoutMilliseconds = 300000) {
    Write-Output "Starting: $File"
    # Use a direct process handle. Shell launching can block before it returns
    # a handle on a noninteractive runner, defeating WaitForExit's timeout.
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo.FileName = $File
    $Process.StartInfo.Arguments = $Arguments -join " "
    $Process.StartInfo.UseShellExecute = $false
    $Process.StartInfo.CreateNoWindow = $true
    $Elapsed = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        if (-not $Process.Start()) { throw "Could not start: $File" }
        $NextProgress = 15000
        while (-not $Process.WaitForExit(1000)) {
            if ($Elapsed.ElapsedMilliseconds -ge $TimeoutMilliseconds) {
                $Process.Kill()
                throw "Process timed out: $File"
            }
            if ($Elapsed.ElapsedMilliseconds -ge $NextProgress) {
                Write-Output "Waiting for $File ($([int]$Elapsed.Elapsed.TotalSeconds)s)"
                $NextProgress += 15000
            }
        }
        if ($Process.ExitCode -ne 0) {
            throw "Process failed ($($Process.ExitCode)): $File"
        }
        Write-Output "Completed: $File"
    }
    finally {
        $Elapsed.Stop()
        $Process.Dispose()
    }
}

function Assert-Installation([string]$Version) {
    Write-Output "Checking installed version $Version and running packaged smoke test"
    $Executable = Join-Path $InstallDirectory "Dnd5eCombatSimulator.exe"
    if (-not (Test-Path -LiteralPath $Executable)) {
        throw "Installed executable is missing."
    }
    $Registration = Get-ItemProperty -LiteralPath $RegistryPath
    if ($Registration.DisplayVersion -ne $Version) {
        throw "Expected installed version $Version, got $($Registration.DisplayVersion)."
    }
    if ((Get-FileHash -LiteralPath $Executable).Hash -ne
        (Get-FileHash -LiteralPath (Join-Path $ProjectDirectory "dist\Dnd5eCombatSimulator.exe")).Hash) {
        throw "Installed executable differs from the release payload."
    }
    Invoke-CheckedProcess $Executable @("--smoke-test")
}

Push-Location $ProjectDirectory
$Transcript = Join-Path $ProjectDirectory "dist\installer-lifecycle.log"
Start-Transcript -Path $Transcript -Force | Out-Null
try {
    $Version = (& $Python scripts\project_version.py).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $Version) { throw "Cannot read application version." }
    $Compiler = Get-Command ISCC.exe -ErrorAction Stop
    # A synthetic older installer exercises the same AppId's upgrade path.
    # Its payload is the current build; historical binary compatibility is separate.
    Write-Output "Compiling synthetic baseline installer"
    Invoke-CheckedProcess $Compiler.Source @("/DAppVersion=0.0.0",
        ('/O"' + $TestRoot + '"'), "packaging\installer.iss")
    $Baseline = Join-Path $TestRoot "Dnd5eCombatSimulator-Setup-0.0.0.exe"
    $Candidate = Join-Path $ProjectDirectory "dist\installer\Dnd5eCombatSimulator-Setup-$Version.exe"
    $Common = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
        ('/DIR="' + $InstallDirectory + '"'), "/NOICONS", "/TASKS=!desktopicon")
    Write-Output "Phase: clean install"
    Invoke-CheckedProcess $Baseline ($Common + ('/LOG="' + $TestRoot + '\clean-install.log"'))
    Assert-Installation "0.0.0"
    Write-Output "Phase: upgrade"
    Invoke-CheckedProcess $Candidate ($Common + ('/LOG="' + $TestRoot + '\upgrade.log"'))
    Assert-Installation $Version
    $Uninstaller = Join-Path $InstallDirectory "unins000.exe"
    Write-Output "Phase: uninstall"
    Invoke-CheckedProcess $Uninstaller @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
        ('/LOG="' + $TestRoot + '\uninstall.log"'))
    # Inno's uninstaller can delegate deletion to a child process.
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ((Test-Path -LiteralPath $InstallDirectory) -and [DateTime]::UtcNow -lt $Deadline) {
        Start-Sleep -Milliseconds 250
    }
    if ((Test-Path -LiteralPath $InstallDirectory) -or (Test-Path -LiteralPath $RegistryPath)) {
        throw "Uninstall left application files or registration behind."
    }
    Write-Output "Clean install, synthetic-baseline upgrade, installed smoke tests, and uninstall passed."
}
finally {
    Write-Output "Collecting installer logs from $TestRoot"
    Copy-Item -Path (Join-Path $TestRoot "*.log") -Destination (Join-Path $ProjectDirectory "dist") -ErrorAction SilentlyContinue
    Stop-Transcript | Out-Null
    Pop-Location
}
