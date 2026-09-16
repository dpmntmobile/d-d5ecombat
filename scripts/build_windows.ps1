param(
    [string]$Python = ".venv\Scripts\python.exe",
    [switch]$SkipDependencyInstall,
    [switch]$Sign,
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectDirectory $Python

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python interpreter not found: $PythonPath"
}

Push-Location $ProjectDirectory
try {
    if (-not $SkipDependencyInstall) {
        & $PythonPath -m pip install -e ".[package]"
        if ($LASTEXITCODE -ne 0) {
            throw "Package dependency installation failed with exit code $LASTEXITCODE"
        }
    }

    & $PythonPath -m PyInstaller --clean --noconfirm packaging\combat_simulator.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    $SmokeProcess = Start-Process -FilePath "dist\Dnd5eCombatSimulator.exe" -ArgumentList "--smoke-test" -WindowStyle Hidden -Wait -PassThru
    if ($SmokeProcess.ExitCode -ne 0) {
        throw "Packaged application smoke test failed with exit code $($SmokeProcess.ExitCode)"
    }

    if ($Sign) {
        & (Join-Path $PSScriptRoot "sign_windows.ps1") -File "dist\Dnd5eCombatSimulator.exe"
    }
    if ($Installer) {
        $AppVersion = (& $PythonPath scripts\project_version.py).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $AppVersion) {
            throw "Could not read the application version"
        }
        $InnoCompiler = Get-Command ISCC.exe -ErrorAction Stop
        & $InnoCompiler.Source "/DAppVersion=$AppVersion" packaging\installer.iss
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup failed with exit code $LASTEXITCODE"
        }
        if ($Sign) {
            $Setup = Get-ChildItem -LiteralPath "dist\installer" -Filter "*.exe" | Select-Object -First 1
            & (Join-Path $PSScriptRoot "sign_windows.ps1") -File $Setup.FullName
        }
    }
}
finally {
    Pop-Location
}

Write-Output "Built dist\Dnd5eCombatSimulator.exe"
