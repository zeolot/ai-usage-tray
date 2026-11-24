@echo off
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0run.pyw" %*
    exit /b 0
)

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw "%~dp0run.pyw" %*
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python "%~dp0run.py" %*
    exit /b 0
)

echo [ERROR] Python 3 with PyQt5 not found. Please install Python 3 and run:
echo     pip install -r requirements.txt
pause
exit /b 1
