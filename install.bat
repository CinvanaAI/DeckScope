@echo off
REM ===================================================================
REM  DeckScope installer for Windows
REM  Double-click this file. It does everything.
REM ===================================================================
setlocal enabledelayedexpansion
title DeckScope Installer
cd /d "%~dp0"

echo.
echo  ==============================================================
echo    DeckScope - Installer
echo  ==============================================================
echo.
echo   This will:
echo     1. Check that Python is installed
echo     2. Install DeckScope into its own private folder
echo     3. Put shortcuts on your Desktop
echo     4. Walk you through setup, step by step
echo.
echo   Nothing outside this folder and your Desktop is changed.
echo.
pause

REM ---------- 1. Find Python -----------------------------------------
echo.
echo  [1/4] Looking for Python...
set PY=
for %%C in (py python python3) do (
  if not defined PY (
    %%C -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
    if !errorlevel! equ 0 set PY=%%C
  )
)

if not defined PY (
  echo.
  echo   Python 3.9 or newer was not found.
  echo.
  echo   Opening the Python download page. Install it, and be sure to tick
  echo   "Add python.exe to PATH" on the first screen. Then run this
  echo   installer again.
  echo.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)
echo        Found: %PY%

REM ---------- 2. Virtual environment ---------------------------------
echo.
echo  [2/4] Setting up a private Python environment...
echo        ^(this keeps DeckScope from interfering with anything else^)
if not exist ".venv" (
  %PY% -m venv .venv
  if errorlevel 1 (
    echo   Could not create the environment. See the message above.
    pause
    exit /b 1
  )
)
set VENVPY=%CD%\.venv\Scripts\python.exe

echo.
echo  [3/4] Installing DeckScope and its components...
echo        ^(this takes a minute or two the first time^)
"%VENVPY%" -m pip install --upgrade pip --quiet
"%VENVPY%" -m pip install -e ".[all]" --quiet
if errorlevel 1 (
  echo.
  echo   Installation failed. Common causes:
  echo     - no internet connection
  echo     - a corporate firewall blocking pip
  echo   The full error is above.
  pause
  exit /b 1
)
echo        Done.

REM ---------- 3. Desktop shortcuts -----------------------------------
echo.
echo  [4/4] Creating Desktop shortcuts...
set LAUNCH=%CD%\DeckScope.bat
> "%LAUNCH%" echo @echo off
>>"%LAUNCH%" echo cd /d "%CD%"
>>"%LAUNCH%" echo "%VENVPY%" -m deckscope app
>>"%LAUNCH%" echo pause

set SETUPBAT=%CD%\DeckScope Setup.bat
> "%SETUPBAT%" echo @echo off
>>"%SETUPBAT%" echo cd /d "%CD%"
>>"%SETUPBAT%" echo "%VENVPY%" -m deckscope setup
>>"%SETUPBAT%" echo pause

powershell -NoProfile -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell);" ^
  "$l=$s.CreateShortcut(\"$d\DeckScope.lnk\");" ^
  "$l.TargetPath='%LAUNCH%'; $l.WorkingDirectory='%CD%';" ^
  "$l.Description='Analyze a pitch deck against its market'; $l.Save();" ^
  "$l2=$s.CreateShortcut(\"$d\DeckScope Setup.lnk\");" ^
  "$l2.TargetPath='%SETUPBAT%'; $l2.WorkingDirectory='%CD%';" ^
  "$l2.Description='Configure DeckScope'; $l2.Save()" >nul 2>&1
echo        Added "DeckScope" and "DeckScope Setup" to your Desktop.

REM ---------- 4. Run the wizard --------------------------------------
echo.
echo  ==============================================================
echo    Installed. Now let's set it up.
echo  ==============================================================
echo.
"%VENVPY%" -m deckscope setup

echo.
echo  ==============================================================
echo    All done.
echo.
echo    Double-click "DeckScope" on your Desktop any time to open it.
echo  ==============================================================
echo.
pause
