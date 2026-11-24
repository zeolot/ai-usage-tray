@echo off
setlocal
cd /d "%~dp0"

echo Building standalone Windows executable (AIUsageTray.exe)...
python -m pip install --quiet pyinstaller PyQt5
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --noconsole ^
    --name AIUsageTray ^
    --icon "%~dp0assets\icon.ico" ^
    "%~dp0run.pyw"

if %errorlevel%==0 (
    echo.
    echo Build succeeded: "%~dp0dist\AIUsageTray.exe"
) else (
    echo Build failed!
)
pause
