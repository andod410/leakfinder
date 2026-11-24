@echo off
REM Dubbelklicka for att starta PLO-lackfinnaren pa Windows.
REM Saknas Python installeras det automatiskt med winget (inbyggt i Windows 10/11).
cd /d "%~dp0"
echo Startar PLO-lackfinnaren fran mappen: %CD%
set PYTHONIOENCODING=utf-8
set PY=
call :findpy
if defined PY goto :havepy
where winget >nul 2>&1
if errorlevel 1 goto :nopy
echo.
echo Python saknas pa datorn. Installerar Python 3.12 automatiskt (tar en till tva minuter)...
echo Om Windows fragar om lov, svara Ja.
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :findpy
if defined PY goto :havepy
:nopy
echo Python 3.10 eller nyare saknas och kunde inte installeras automatiskt.
echo Installera fran https://www.python.org/downloads/ och kryssa i "Add python.exe to PATH".
start "" https://www.python.org/downloads/
pause
exit /b 1
:havepy
echo Anvander Python: %PY%
REM Egen miljo for Windows (.venv-win), sa att samma mapp kan anvandas pa Mac och Windows.
set VENV=.venv-win
if exist .venv\Scripts\python.exe set VENV=.venv
if not exist %VENV%\Scripts\python.exe (
  echo Forbereder forsta starten, tar nagon minut...
  %PY% -m venv %VENV% || (pause & exit /b 1)
)
%VENV%\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || (pause & exit /b 1)
%VENV%\Scripts\python -m plo_leak.web --open
REM Stangdes programmet av en nyare version (eller normalt) stangs fonstret direkt.
REM Bara vid ett fel star fonstret kvar, sa att felet gar att lasa.
if errorlevel 1 pause
exit /b 0

:findpy
REM Hitta Python 3.10+: py-startaren, python i PATH, eller en nyss installerad Python (som PATH inte ser an).
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && (set PY=py -3& exit /b 0)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && (set PY=python& exit /b 0)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if exist "%%D\python.exe" "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set PY="%%D\python.exe"
)
exit /b 0
