@echo off
echo ==========================================
echo   AI Timetable Scheduler - Robust Launcher
echo ==========================================

echo.
echo [1/3] Setting up virtual environment...
if exist "Z:\" subst Z: /d
subst Z: "%~dp0backend"

echo.
echo [1.5/3] Checking Dependencies...
start /wait cmd /c "Z:\venv_short\Scripts\pip install --no-cache-dir -r Z:\requirements.txt"

echo.
echo [2/3] Starting Backend Server...
start "AI Timetable Backend" cmd /k "set PYTHONPATH=Z:\pkg && Z:\venv_short\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

echo.
echo [3/3] Starting Frontend Server...
cd "frontend"
start "AI Timetable Frontend" cmd /k "npm run dev"

echo.
echo ==========================================
echo   Servers launched!
echo   Frontend: http://localhost:3002
echo   Login: admin / admin123
echo ==========================================
pause
