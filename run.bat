@echo off
setlocal enabledelayedexpansion
title Epstein Document Scraper
color 0A

echo ================================================================
echo   EPSTEIN DOCUMENT SCRAPER - One-Click Setup
echo ================================================================
echo.

:: ── Locate or install Python ────────────────────────────────────
:: First check if a local embedded Python exists (from previous run)
set "LOCALPY=%~dp0python\python.exe"
if exist "%LOCALPY%" (
    echo   Using local Python installation.
    set "PYTHON=%LOCALPY%"
    goto :have_python
)

:: Check if system Python is available
where python >nul 2>nul
if %errorlevel% equ 0 (
    echo   Using system Python.
    set "PYTHON=python"
    goto :have_python
)

:: ── No Python found — download embedded Python ──────────────────
echo   Python not found. Downloading portable Python (one-time, ~25MB)...
echo.

set "PYVER=3.12.2"
set "PYZIP=python-%PYVER%-embed-amd64.zip"
set "PYURL=https://www.python.org/ftp/python/%PYVER%/%PYZIP%"
set "PYDIR=%~dp0python"

:: Download using PowerShell (available on all modern Windows)
powershell -NoProfile -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%~dp0%PYZIP%'"
if %errorlevel% neq 0 (
    echo   [ERROR] Failed to download Python. Check your internet connection.
    pause
    exit /b 1
)

:: Extract
echo   Extracting Python...
powershell -NoProfile -Command "Expand-Archive -Path '%~dp0%PYZIP%' -DestinationPath '%PYDIR%' -Force"
del "%~dp0%PYZIP%" >nul 2>nul

:: Enable pip in embedded Python (uncomment import site in python312._pth)
powershell -NoProfile -Command ^
    "$pth = Get-ChildItem '%PYDIR%\python*._pth' | Select-Object -First 1; if ($pth) { (Get-Content $pth.FullName) -replace '#import site','import site' | Set-Content $pth.FullName }"

:: Install pip
echo   Installing pip...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%~dp0get-pip.py'"
"%PYDIR%\python.exe" "%~dp0get-pip.py" --quiet >nul 2>nul
del "%~dp0get-pip.py" >nul 2>nul

set "PYTHON=%PYDIR%\python.exe"
echo   Portable Python installed successfully.
echo.

:have_python

:: ── Create venv (skip for embedded Python without venv module) ──
:: For embedded Python, we install directly; for system Python, use venv
echo %PYTHON% | findstr /i "python\\python.exe" >nul
if %errorlevel% equ 0 (
    :: Embedded Python — install packages directly
    set "PIP=%~dp0python\Scripts\pip.exe"
    set "PW=%~dp0python\Scripts\playwright.exe"
    goto :install_deps
)

:: System Python — use virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo   Creating virtual environment...
    %PYTHON% -m venv .venv
)
call .venv\Scripts\activate.bat
set "PYTHON=python"
set "PIP=pip"
set "PW=playwright"

:install_deps
:: ── Install dependencies ────────────────────────────────────────
echo   Installing dependencies (this may take a minute on first run)...
"%PIP%" install --quiet --upgrade pip >nul 2>nul
"%PIP%" install --quiet -r "%~dp0requirements.txt" >nul 2>nul
if %errorlevel% neq 0 (
    echo   Retrying package install with output...
    "%PIP%" install -r "%~dp0requirements.txt"
)

:: ── Install Firefox browser ────────────────────────────────────
echo   Checking Firefox browser for Playwright...
"%PW%" install firefox >nul 2>nul
if %errorlevel% neq 0 (
    echo   Installing Firefox browser (one-time, ~80MB download)...
    "%PYTHON%" -m playwright install firefox
)
echo   All dependencies ready.

:: ── Ask for search query ────────────────────────────────────────
echo.
echo ================================================================
echo   SETUP COMPLETE - Ready to search
echo ================================================================
echo.
echo   Enter one or more search terms separated by spaces.
echo   Examples:
echo     passport
echo     trump
echo     minor children trafficking
echo.
set /p "QUERY=  Search for: "

if "%QUERY%"=="" (
    echo.
    echo   [ERROR] No search term entered. Exiting.
    pause
    exit /b 1
)

:: ── Run the scraper ─────────────────────────────────────────────
echo.
echo   Starting scraper for: %QUERY%
echo   (A Firefox window will open - don't close it!)
echo.

"%PYTHON%" "%~dp0scrape.py" %QUERY% -o results

echo.
echo ================================================================
echo   DONE! Results are in the "results" folder:
echo     results\pdfs\    - Downloaded PDF files
echo     results\texts\   - Extracted plain text
echo ================================================================
echo.
pause
