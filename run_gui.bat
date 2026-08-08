@echo off
rem Launch the COMPAS GUI using the project's virtual environment.
cd /d "%~dp0"
start "" "C:\Users\seric\.venvs\compas\Scripts\pythonw.exe" -m compas_gui
