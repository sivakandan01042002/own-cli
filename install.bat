@echo off
setlocal enabledelayedexpansion

echo.
echo ===================================================
echo       Installing QueryNest Coding Assistant        
echo ===================================================
echo.

set "INSTALL_DIR=%USERPROFILE%\.querynest"
set "BIN_DIR=%INSTALL_DIR%\bin"
set "VENV_DIR=%INSTALL_DIR%\venv"

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python 3.10+ is required but not found in PATH.
    echo Please install Python from https://www.python.org/downloads/ and check "Add Python to PATH".
    pause
    exit /b 1
)

:: If run from within the repo directory, install directly from local source
if exist "%~dp0pyproject.toml" (
    echo [*] Installing QueryNest from local repository...
    python -m pip install -e "%~dp0."
    
    :: Generate direct wrapper
    (
        echo @echo off
        echo python -m app.cli %%*
    ) > "%BIN_DIR%\querynest.bat"
) else (
    :: Standalone installation via virtual environment
    if not exist "%VENV_DIR%" (
        echo [*] Creating isolated virtual environment in %VENV_DIR%...
        python -m venv "%VENV_DIR%"
    )
    echo [*] Installing QueryNest and dependencies...
    call "%VENV_DIR%\Scripts\activate.bat"
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install git+https://github.com/sivak/querynest.git
    
    (
        echo @echo off
        echo call "%VENV_DIR%\Scripts\activate.bat"
        echo python -m app.cli %%*
    ) > "%BIN_DIR%\querynest.bat"
)

:: Initialize default config if missing
if not exist "%INSTALL_DIR%\.env" (
    echo [*] Creating default ~/.querynest/.env template...
    (
        echo # QueryNest Global Environment Configuration
        echo GEMINI_API_KEY=
        echo GROQ_API_KEY=
        echo DEFAULT_PROVIDER=gemini
        echo REDIS_URL=redis://localhost:6379/0
    ) > "%INSTALL_DIR%\.env"
)

:: Add ~/.querynest/bin to permanent User PATH if not present
echo %PATH% | find /i "%BIN_DIR%" >nul
if %ERRORLEVEL% NEQ 0 (
    echo [*] Adding %BIN_DIR% to user PATH...
    for /f "tokens=2*" %%a in ('reg query HKCU\Environment /v PATH 2^>nul') do set "USER_CURRENT_PATH=%%b"
    if defined USER_CURRENT_PATH (
        setx PATH "%USER_CURRENT_PATH%;%BIN_DIR%" >nul
    ) else (
        setx PATH "%BIN_DIR%" >nul
    )
    set "PATH=%PATH%;%BIN_DIR%"
)

echo.
echo ===================================================
echo   QueryNest has been successfully installed!       
echo ===================================================
echo.
echo You can now run QueryNest anytime by typing:
echo.
echo   querynest
echo.
pause
