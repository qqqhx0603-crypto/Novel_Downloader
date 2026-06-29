@echo off
setlocal
cd /d "%~dp0"
start "" pythonw.exe "%~dp0gui\smart_downloader_gui.py"
endlocal
