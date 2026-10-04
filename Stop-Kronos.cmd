@echo off
powershell.exe -NoProfile -File "%~dp0Stop-Kronos.ps1"
if errorlevel 1 pause
