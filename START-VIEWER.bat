@echo off
setlocal
cd /d "%~dp0"
title Offline Chat Viewer
if exist ".semantic-env\Scripts\python.exe" (
  ".semantic-env\Scripts\python.exe" viewer.py %*
  goto done
)
if exist "runtime\python.exe" (
  "runtime\python.exe" viewer.py %*
  goto done
)
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 viewer.py %*
  goto done
)
where python >nul 2>nul
if %errorlevel% equ 0 (
  python viewer.py %*
  goto done
)
echo Python could not be found. Extract the entire ZIP, including the runtime folder.
echo Alternatively install Python 3.10 or newer from https://www.python.org/downloads/windows/
pause
exit /b 1
:done
if %errorlevel% neq 0 (
  echo.
  echo The viewer could not start. The error is shown above.
  pause
)
