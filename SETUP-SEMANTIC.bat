@echo off
setlocal
cd /d "%~dp0"
title Local semantic search setup
if exist "runtime\python.exe" (
  "runtime\python.exe" setup_semantic.py
) else (
  python setup_semantic.py
)
if errorlevel 1 (
  echo Setup interrupted. Run this again to retry; the standard viewer still works.
  pause
  exit /b 1
)
echo Ready. You can select Semantic in the viewer now. No restart is needed.
pause
