@echo off
rem Build the Windows executable into dist\COMPAS\COMPAS.exe.
rem Uses the project venv; installs PyInstaller there on first run.
setlocal
cd /d "%~dp0.."

set PY=C:\Users\seric\.venvs\compas\Scripts\python.exe
if not exist "%PY%" set PY=python

"%PY%" -m pip install --quiet pyinstaller
"%PY%" -m PyInstaller packaging\compas.spec --noconfirm
if errorlevel 1 exit /b 1

echo.
echo Done: dist\COMPAS\COMPAS.exe
endlocal
