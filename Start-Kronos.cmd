@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing project environment. See WINDOWS-QUICKSTART.md.
  pause
  exit /b 1
)
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set HF_HUB_CACHE=%~dp0.cache\huggingface
set HF_XET_CACHE=%~dp0.cache\xet
set HF_HUB_OFFLINE=1
echo Kronos: http://127.0.0.1:7070
echo Open that address in your browser. Press Ctrl+C here to stop.
".venv\Scripts\python.exe" scripts\run_webui.py %*
if errorlevel 1 pause
