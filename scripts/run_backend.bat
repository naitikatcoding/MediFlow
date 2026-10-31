@echo off
echo ========================================================
echo Starting MediFlow FastAPI Backend Service (Port 8000)...
echo ========================================================

cd /d "%~dp0..\Backend"

IF EXIST ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py
) ELSE (
    python run.py
)
