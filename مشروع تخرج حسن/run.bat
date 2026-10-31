@echo off
title Financial Statement Analyzer
cd /d "%~dp0"

echo ============================================
echo    Financial Statement Analysis Agent
echo ============================================
echo.

REM ---- 0) Note about double-launch ----
echo (If the app is already open in another black window, just use it —
echo  a second instance cannot share the same port.)

REM ---- 1) Python present? ----
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on this PC.
    echo        Install Python 3.11+ from python.org and check
    echo        "Add python.exe to PATH" during setup, then run again.
    echo.
    pause
    exit /b 1
)

REM ---- 2) Create the virtual environment on first run ----
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment - first run only...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: could not create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Virtual environment found.
)

REM ---- 3) Install dependencies if ANY core library is missing ----
set MISSING=0
".venv\Scripts\python.exe" -c "import streamlit, cv2, pypdfium2, pdfplumber, openpyxl, xlrd, plotly, pandas, google.genai, dotenv" >nul 2>&1 || set MISSING=1

if "%MISSING%"=="1" (
    echo [2/3] Installing / updating dependencies - first run only, few minutes...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Installation failed. Check your internet connection and run again.
        pause
        exit /b 1
    )
) else (
    echo [2/3] All dependencies ready ^(including vision layer^).
)

REM ---- 4) Make sure the .env file exists ----
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [3/3] Created .env from the template.
        echo        Open .env and put your GEMINI_API_KEYS inside it.
    ) else (
        echo [3/3] WARNING: no .env file - AI features will be disabled.
    )
) else (
    echo [3/3] .env found - API keys loaded.
)

echo.
echo ============================================================
echo   Starting the dashboard...
echo   The browser will open at http://localhost:8501
echo   Keep this window OPEN while using the app.
echo   Close this window to stop the app.
echo ============================================================
echo.

".venv\Scripts\python.exe" -m streamlit run app.py

echo.
echo The app was closed.
pause
