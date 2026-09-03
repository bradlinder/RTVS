@echo off
setlocal enabledelayedexpansion

echo =====================================================================
echo  Radio ^& TV Story Segmenter v1.6 - Automated 1-Click Build (Windows)
echo =====================================================================
echo.

:: 1. Navigate to repository root directory
cd /d "%~dp0"

:: 2. Check for Python installation
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=py -3"
    goto :PYTHON_FOUND
)

where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
    goto :PYTHON_FOUND
)

echo [ERROR] Python 3.10+ was not found on your PATH.
echo Please install Python 3.10 or higher from https://python.org and ensure
echo "Add Python to PATH" is checked during setup.
echo.
pause
exit /b 1

:PYTHON_FOUND
echo [1/4] Checking Python environment...
%PYTHON_EXE% -c "import sys; print('Using Python ' + sys.version.split()[0])"

:: 3. Setup or verify isolated build virtual environment
if not exist ".venv-build" (
    echo [2/4] Creating dedicated build virtual environment (.venv-build)...
    %PYTHON_EXE% -m venv .venv-build
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [2/4] Using existing build virtual environment (.venv-build)...
)

:: Activate the venv
call .venv-build\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

:: Upgrade pip and install build dependencies
echo [3/4] Installing / verifying lightweight CPU build dependencies...
python -m pip install --upgrade pip --quiet
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu --quiet
pip install -r requirements.txt -r requirements-build.txt --quiet

:: 4. Execute build script
echo [4/4] Running PyInstaller binary compilation...
python build_installer.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Compilation failed. See output above for details.
    pause
    exit /b 1
)

:: 5. Optional Inno Setup compilation if ISCC is installed
set "ISCC_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
) else (
    where iscc >nul 2>nul
    if %ERRORLEVEL% equ 0 set "ISCC_PATH=iscc"
)

if defined ISCC_PATH (
    echo.
    echo [BONUS] Inno Setup compiler found at "!ISCC_PATH!".
    echo Compiling Windows setup installer executable...
    "!ISCC_PATH!" installer\Windows\RadioTVStorySegmenter.iss
    if %ERRORLEVEL% equ 0 (
        echo [SUCCESS] Windows Installer created in installer\Windows\Output\
    )
) else (
    echo.
    echo [INFO] Inno Setup (ISCC.exe) not detected. To compile the Windows .exe installer,
    echo install Inno Setup 6 from https://jrsoftware.org/isdl.php
)

echo.
echo =====================================================================
echo  BUILD COMPLETE! Standalone application is located in: dist\RadioTVSegmenter\
echo =====================================================================
echo.
pause
