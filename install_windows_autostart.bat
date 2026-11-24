@echo off
setlocal
cd /d "%~dp0"

if /i "%~1"=="--uninstall" (
    python "%~dp0run.py" --uninstall-autostart
) else (
    python "%~dp0run.py" --install-autostart
)
pause
