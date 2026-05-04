@echo off
REM Simple launcher for users who prefer double-click on Windows
SETLOCAL ENABLEEXTENSIONS
set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%bootstrap.ps1"
ENDLOCAL
