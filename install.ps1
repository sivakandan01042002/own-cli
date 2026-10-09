Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "       Installing QueryNest Coding Assistant        " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$InstallDir = "$HOME\.querynest"
$BinDir = "$InstallDir\bin"
$VenvDir = "$InstallDir\venv"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Python 3.10+ is required but not found in PATH." -ForegroundColor Red
    Write-Host "Please install Python from https://www.python.org/downloads/ and check 'Add Python to PATH'." -ForegroundColor Yellow
    exit 1
}

# If run from within local repo
if (Test-Path "$ScriptDir\pyproject.toml") {
    Write-Host "[*] Installing QueryNest from local source: $ScriptDir" -ForegroundColor Green
    python -m pip install -e "$ScriptDir"

    $Wrapper = @"
@echo off
python -m app.cli %*
"@
    Set-Content -Path "$BinDir\querynest.bat" -Value $Wrapper
} else {
    # Standalone installation into ~/.querynest/venv
    if (-not (Test-Path $VenvDir)) {
        Write-Host "[*] Creating isolated virtual environment in $VenvDir..." -ForegroundColor Green
        python -m venv $VenvDir
    }
    Write-Host "[*] Installing QueryNest and dependencies..." -ForegroundColor Green
    & "$VenvDir\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
    & "$VenvDir\Scripts\python.exe" -m pip install git+https://github.com/sivak/querynest.git

    $Wrapper = @"
@echo off
call "$VenvDir\Scripts\activate.bat"
python -m app.cli %*
"@
    Set-Content -Path "$BinDir\querynest.bat" -Value $Wrapper
}

# Initialize default ~/.querynest/.env if missing
$UserEnv = "$InstallDir\.env"
if (-not (Test-Path $UserEnv)) {
    Write-Host "[*] Creating default ~/.querynest/.env configuration..." -ForegroundColor Green
    @"
# QueryNest Global Environment Configuration
GEMINI_API_KEY=
GROQ_API_KEY=
DEFAULT_PROVIDER=gemini
REDIS_URL=redis://localhost:6379/0
"@ | Set-Content -Path $UserEnv
}

# Permanently add ~/.querynest/bin to User PATH
$UserPath = [Environment]::GetEnvironmentVariable("PATH", [EnvironmentVariableTarget]::User)
if ($UserPath -notlike "*$BinDir*") {
    Write-Host "[*] Adding $BinDir to User PATH..." -ForegroundColor Green
    [Environment]::SetEnvironmentVariable("PATH", "$UserPath;$BinDir", [EnvironmentVariableTarget]::User)
    $env:PATH += ";$BinDir"
}

Write-Host ""
Write-Host "===================================================" -ForegroundColor Green
Write-Host "   QueryNest has been successfully installed!      " -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Green
Write-Host ""
Write-Host "You can now run QueryNest anytime by typing:" -ForegroundColor Yellow
Write-Host ""
Write-Host "   querynest" -ForegroundColor Cyan
Write-Host ""
