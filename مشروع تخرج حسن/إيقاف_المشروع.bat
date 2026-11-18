@echo off
chcp 65001 >nul
title FinSight — إيقاف المشروع
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_services.ps1"
timeout /t 3 >nul
