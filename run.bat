@echo off
setlocal enabledelayedexpansion
title Epstein Document Scraper
color 0A

echo ================================================================
echo   EPSTEIN DOCUMENT SCRAPER - One-Click Setup
echo ================================================================
echo.

:: ── Check for Python ────────────────────────────────────────────
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo.
    echo   Please install Python 3.10+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)

:: Verify Python version is 3.10+
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   Python found: %PYVER%

:: ── Create virtual environment if needed ────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo   Virtual environment created.
)

:: ── Activate venv ───────────────────────────────────────────────
call .venv\Scripts\activate.bat

:: ── Install dependencies ────────────────────────────────────────
echo.
echo   Installing dependencies (this may take a minute on first run)...
pip install --quiet --upgrade pip >nul 2>nul
pip install --quiet -r requirements.txt >nul 2>nul
if %errorlevel% neq 0 (
    echo   [WARN] Some packages may have failed. Retrying with output...
    pip install -r requirements.txt
)

:: ── Install Firefox browser ────────────────────────────────────
echo   Checking Firefox browser for Playwright...
playwright install firefox >nul 2>nul
if %errorlevel% neq 0 (
    echo   Installing Firefox browser (one-time, ~80MB download)...
    python -m playwright install firefox
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

python scrape.py %QUERY% -o results

echo.
echo ================================================================
echo   DONE! Results are in the "results" folder:
echo     results\pdfs\    - Downloaded PDF files
echo     results\texts\   - Extracted plain text
echo ================================================================
echo.
pause
