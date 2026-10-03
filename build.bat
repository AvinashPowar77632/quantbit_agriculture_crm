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
set "DATA_ARG="
if exist "assets" (
    set "DATA_ARG=--add-data assets;assets"
)
if exist "quantbit_agriculture_crm\public\images" (
    set "DATA_ARG=!DATA_ARG! --add-data quantbit_agriculture_crm\public\images;quantbit_agriculture_crm\public\images"
)

set "ICON_ARG="
if exist "assets\kranti_sugar_logo.ico" (
    set "ICON_ARG=--icon assets\kranti_sugar_logo.ico"
) else if exist "quantbit_agriculture_crm\public\images\kranti_sugar_logo.ico" (
    set "ICON_ARG=--icon quantbit_agriculture_crm\public\images\kranti_sugar_logo.ico"
) else if exist "assets\kranti_sugar_logo.png" (
    set "ICON_ARG=--icon assets\kranti_sugar_logo.png"
)

"%VENV_PY%" -m PyInstaller --noconfirm --onefile --windowed !DATA_ARG! !ICON_ARG! --hidden-import assets_data --hidden-import quantbit_agriculture_crm.assets_data --name "QuantbitCaneWeighbridge" main.py
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

REM --- 6. Create a Desktop shortcut to the exe -----------------------------
REM Written to a temp .ps1 file (run with -File) instead of an inline
REM -Command string - inline nested quotes/carets are fragile across
REM different cmd.exe/PowerShell versions and can silently fail to parse on
REM some machines. [Environment]::GetFolderPath('Desktop') is used instead
REM of %USERPROFILE%\Desktop because that hardcoded path is wrong whenever
REM OneDrive Known Folder Move has redirected the real Desktop elsewhere
REM (common on managed/work PCs) - GetFolderPath always resolves to wherever
REM the Desktop actually is. Success/failure is reported back to this batch
REM script via a temp text file rather than parsed from console output, so
REM this doesn't depend on how a given PowerShell version buffers Write-Host.
echo Creating Desktop shortcut...
set "SHORTCUT_PS1=%TEMP%\quantbit_make_shortcut.ps1"
set "SHORTCUT_INFO=%TEMP%\quantbit_shortcut_result.txt"
if exist "%SHORTCUT_INFO%" del "%SHORTCUT_INFO%" >nul 2>nul

(
    echo param^([string]$ExePath, [string]$InfoFile^)
    echo $ErrorActionPreference = 'Stop'
    echo try {
    echo     $desktop = [Environment]::GetFolderPath^('Desktop'^)
    echo     $lnkPath = Join-Path $desktop 'Quantbit Cane Weighbridge.lnk'
    echo     $shell = New-Object -ComObject WScript.Shell
    echo     $shortcut = $shell.CreateShortcut^($lnkPath^)
    echo     $shortcut.TargetPath = $ExePath
    echo     $shortcut.WorkingDirectory = Split-Path $ExePath -Parent
    echo     $shortcut.IconLocation = "$ExePath,0"
    echo     $shortcut.Description = 'Quantbit Cane Weighbridge System'
    echo     $shortcut.Save^(^)
    echo     Set-Content -Path $InfoFile -Value $lnkPath -Encoding UTF8
    echo } catch {
    echo     Set-Content -Path $InfoFile -Value "ERROR: $($_.Exception.Message)" -Encoding UTF8
    echo }
) > "%SHORTCUT_PS1%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SHORTCUT_PS1%" "%APP_EXE%" "%SHORTCUT_INFO%"
del "%SHORTCUT_PS1%" >nul 2>nul

set "SHORTCUT_RESULT="
if exist "%SHORTCUT_INFO%" (
    set /p SHORTCUT_RESULT=<"%SHORTCUT_INFO%"
    del "%SHORTCUT_INFO%" >nul 2>nul
)

set "SHORTCUT_DONE_LINE=Shortcut:  UNKNOWN - PowerShell may be unavailable/blocked on this machine"
echo !SHORTCUT_RESULT! | find "ERROR:" >nul
if not errorlevel 1 (
    echo WARNING: Could not create the Desktop shortcut automatically.
    echo          !SHORTCUT_RESULT!
    echo          This can happen if your Desktop is redirected by OneDrive, or if
    echo          security software blocks shortcut creation. You can create it
    echo          yourself instead: right-click "%APP_EXE%" -^> Show more options
    echo          -^> Send to -^> Desktop ^(create shortcut^).
    set "SHORTCUT_DONE_LINE=Shortcut:  NOT CREATED - see warning above"
) else if defined SHORTCUT_RESULT (
    echo Desktop shortcut created: !SHORTCUT_RESULT!
    set "SHORTCUT_DONE_LINE=Shortcut:  !SHORTCUT_RESULT!"
)

echo.
echo ================================================================
echo  DONE
echo  EXE:       %APP_EXE%
echo  !SHORTCUT_DONE_LINE!
echo ================================================================
pause
