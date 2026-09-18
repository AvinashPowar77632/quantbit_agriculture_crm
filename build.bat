@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================================
echo  Quantbit Cane Weighbridge - Build EXE + Desktop Shortcut
echo ================================================================
echo Folder: %~dp0
echo.

REM --- 1. Make sure main.py is next to this script ---
if not exist "main.py" (
    echo ERROR: main.py not found in this folder. Put build.bat next to main.py and re-run.
    pause
    exit /b 1
)

REM --- 2. Find/install Python 3 ---
REM (Windows ships a fake "python" alias that just opens the Microsoft Store -
REM  it shows up in "where python" but doesn't run, so it must be filtered out.)
set "PYEXE="
for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | find /i "WindowsApps" >nul
    if errorlevel 1 (
        if not defined PYEXE (
            "%%P" --version >nul 2>nul
            if not errorlevel 1 set "PYEXE=%%P"
        )
    )
)

if not defined PYEXE (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" set "PYEXE=%%D\python.exe"
    )
)

if not defined PYEXE (
    echo Python not found on this machine.
    where winget >nul 2>nul
    if errorlevel 1 (
        echo ERROR: winget is not available either. Please install Python 3.10+ manually from
        echo        https://www.python.org/downloads/  ^(check "Add python.exe to PATH"^), then re-run build.bat.
        pause
        exit /b 1
    )
    echo Installing Python 3.12 via winget ^(one-time, needs internet^)...
    winget install --id Python.Python.3.12 --source winget --accept-source-agreements --accept-package-agreements -e --scope user
    if errorlevel 1 (
        echo ERROR: Automatic Python install failed. Install it manually from https://www.python.org/downloads/ and re-run build.bat.
        pause
        exit /b 1
    )

    REM Try to find it immediately (installer just placed it here) instead of
    REM requiring the user to reopen the window for a PATH refresh.
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" set "PYEXE=%%D\python.exe"
    )

    if not defined PYEXE (
        echo.
        echo Python was just installed. Please CLOSE this window and double-click build.bat again
        echo ^(this refreshes PATH so the new "python" command is picked up^).
        pause
        exit /b 0
    )
)

echo Using Python: %PYEXE%
"%PYEXE%" --version

REM --- 3. Create a project-local virtual environment (keeps things isolated) ---
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    "%PYEXE%" -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

set "VENV_PY=%~dp0venv\Scripts\python.exe"

REM --- 4. Install/upgrade required packages ---
echo Installing dependencies ^(PySide6, pyserial, requests, pyinstaller^)...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install PySide6 pyserial requests pyinstaller
if errorlevel 1 (
    echo ERROR: Dependency installation failed. Check your internet connection.
    pause
    exit /b 1
)

REM --- 5. Build the standalone exe ---
echo Building QuantbitCaneWeighbridge.exe ...
"%VENV_PY%" -m PyInstaller --noconfirm --onefile --windowed --name "QuantbitCaneWeighbridge" main.py
if errorlevel 1 (
    echo ERROR: PyInstaller build failed. See the output above.
    pause
    exit /b 1
)

set "APP_EXE=%~dp0dist\QuantbitCaneWeighbridge.exe"
if not exist "%APP_EXE%" (
    echo ERROR: Build finished but exe was not found at %APP_EXE%
    pause
    exit /b 1
)

REM --- 6. Create a Desktop shortcut to the exe ---
echo Creating Desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$exe = '%APP_EXE%'; $s = (New-Object -ComObject WScript.Shell).CreateShortcut(\"$env:USERPROFILE\Desktop\Quantbit Cane Weighbridge.lnk\"); $s.TargetPath = $exe; $s.WorkingDirectory = Split-Path $exe -Parent; $s.IconLocation = \"$exe,0\"; $s.Description = 'Quantbit Cane Weighbridge System'; $s.Save()"

echo.
echo ================================================================
echo  DONE
echo  EXE:       %APP_EXE%
echo  Shortcut:  %%USERPROFILE%%\Desktop\Quantbit Cane Weighbridge.lnk
echo ================================================================
pause
