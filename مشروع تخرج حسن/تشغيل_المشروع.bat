@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title FinSight — مشغل المشروع
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [!] البيئة غير جاهزة — شغّل run.bat مرة واحدة أولًا لإعداد البيئة.
    pause
    exit /b 1
)

:menu
cls
echo ============================================
echo    FinSight — تحليل القوائم المالية
echo ============================================
echo.
echo   [1] واجهة التحليل في المتصفح
echo   [2] بوت تليجرام
echo   [3] الاثنان معًا
echo   [0] خروج من القائمة (الخدمات تستمر)
echo.
set "choice="
set /p choice=اختر رقمًا ثم Enter: 

if "%choice%"=="1" goto web
if "%choice%"=="2" goto bot
if "%choice%"=="3" goto both
if "%choice%"=="0" exit /b 0
goto menu

:web
call :ensure_server
start "" "http://localhost:8501"
echo [✓] الواجهة تعمل في المتصفح — الخادم في النافذة المصغرة.
echo     للإيقاف الكامل: شغّل إيقاف_المشروع.bat
timeout /t 3 >nul
exit /b 0

:bot
start "FinSight — بوت تليجرام" "%PY%" bot.py
echo [✓] البوت يعمل في نافذته — أرسل الملف من تليجرام.
echo     للإيقاف الكامل: شغّل إيقاف_المشروع.bat
timeout /t 3 >nul
exit /b 0

:both
call :ensure_server
start "" "http://localhost:8501"
start "FinSight — بوت تليجرام" "%PY%" bot.py
echo [✓] الواجهة والبوت يعملان.
echo     للإيقاف الكامل: شغّل إيقاف_المشروع.bat
timeout /t 3 >nul
exit /b 0

:ensure_server
netstat -ano | findstr ":8501 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [✓] الخادم يعمل أصلًا — فتح المتصفح فقط.
    goto :eof
)
echo [..] تشغيل الخادم — انتظر حتى يصبح جاهزًا...
start "FinSight — الخادم" /min "%PY%" -m streamlit run app.py
set /a waited=0
:waitloop
timeout /t 1 >nul
netstat -ano | findstr ":8501 " | findstr "LISTENING" >nul
if errorlevel 1 (
    set /a waited+=1
    if !waited! lss 30 goto waitloop
)
netstat -ano | findstr ":8501 " | findstr "LISTENING" >nul
if errorlevel 1 (
    echo [!] الخادم لم يستجيب خلال 30 ثانية — راجع النافذة المصغرة.
) else (
    echo [✓] الخادم جاهز.
)
goto :eof
