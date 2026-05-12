@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required. Install Python or set PATH, then run again.
  pause
  exit /b 1
)
python -m puppet_forge.app
pause

