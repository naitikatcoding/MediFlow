@echo off
echo ========================================================
echo Starting MediFlow Next.js Frontend (Port 3000)...
echo ========================================================

cd /d "%~dp0..\Frontend"
npm run dev
