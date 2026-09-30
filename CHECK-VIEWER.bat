@echo off
setlocal
cd /d "%~dp0"
title Offline Chat Viewer - Diagnostic check
if exist "runtime\python.exe" (
  "runtime\python.exe" diagnose_viewer.py %*
  goto done
)
if exist ".semantic-env\Scripts\python.exe" (
  ".semantic-env\Scripts\python.exe" diagnose_viewer.py %*
  goto done
)
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 diagnose_viewer.py %*
  goto done
)
where python >nul 2>nul
if %errorlevel% equ 0 (
  python diagnose_viewer.py %*
  goto done
)
echo Copy these checker files beside START-VIEWER.bat in the extracted viewer folder.
echo The existing runtime folder must be present, or Python must be installed.
:done
echo.
pause
