@echo off
title Physics Experiment - Setup
echo ========================================
echo   Physics Experiment - Setup
echo ========================================
echo.

echo [1/3] Checking Python...
python --version >nul 2>&1
if not errorlevel 1 (
    python --version
    goto :step2
)

echo       Searching for Python on disk...
set "PYTHON_EXE="
for /d %%d in (
    "%LOCALAPPDATA%\Programs\Python\Python3*"
    "%ProgramFiles%\Python\Python3*"
    "%ProgramFiles(x86)%\Python\Python3*"
    "C:\Python\Python3*"
    "C:\Python3*"
) do if not defined PYTHON_EXE if exist "%%d\python.exe" set "PYTHON_EXE=%%d\python.exe"

if defined PYTHON_EXE (
    echo       Found: %PYTHON_EXE%
    for %%f in ("%PYTHON_EXE%") do set "PYTHON_DIR=%%~dpf"
    goto :fix_path
)

where winget >nul 2>&1
if errorlevel 1 goto :no_python

echo       Installing Python 3.12 via winget...
winget install Python.Python.3.12 --silent --accept-package-agreements --disable-interactivity --source winget
if errorlevel 1 (
    winget install Python.Python.3.12 --silent --accept-package-agreements --disable-interactivity
    if errorlevel 1 goto :winget_fail
)

set "PYTHON_EXE="
for /d %%d in (
    "%LOCALAPPDATA%\Programs\Python\Python3*"
    "%ProgramFiles%\Python\Python3*"
) do if not defined PYTHON_EXE if exist "%%d\python.exe" set "PYTHON_EXE=%%d\python.exe"

if not defined PYTHON_EXE goto :need_restart

for %%f in ("%PYTHON_EXE%") do set "PYTHON_DIR=%%~dpf"
echo       Installed: %PYTHON_EXE%

:fix_path
echo       Adding Python to user PATH...
set "PYTHON_DIR=%PYTHON_DIR:~0,-1%"
setx PATH "%PYTHON_DIR%;%PYTHON_DIR%Scripts;%PATH%" >nul 2>&1
set "PATH=%PYTHON_DIR%;%PYTHON_DIR%Scripts;%PATH%"
python --version >nul 2>&1
if not errorlevel 1 (
    echo       Python is now available.
    goto :step2
)

echo [WARN] PATH updated, but a new CMD window is needed.
echo        Setup will continue; run.bat works in a fresh window.
echo.

:step2
echo.
echo [2/3] Configuring pip mirror (Tsinghua)...
python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
python -m pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

echo.
echo [3/3] Installing dependencies...
python -m pip install openpyxl matplotlib python-docx pywin32
if not errorlevel 1 goto :done

echo [WARN] Mirror failed, retrying with default...
python -m pip install openpyxl matplotlib python-docx pywin32
if not errorlevel 1 goto :done

echo [ERROR] Installation failed. Try Run as Administrator.
pause
exit /b 1

:done
echo.
echo ========================================
echo   Setup complete!
echo ========================================
echo.
pause
exit /b 0

:need_restart
echo [INFO] Python installed. Please re-run this script after restart.
pause
exit /b 0

:no_python
echo [ERROR] Python not found and winget not available.
echo        Install Python from: https://www.python.org/downloads/
echo        (Check "Add Python to PATH" during install)
pause
exit /b 1

:winget_fail
echo [ERROR] winget failed to install Python.
echo        Install manually from: https://www.python.org/downloads/
pause
exit /b 1
