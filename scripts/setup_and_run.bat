@echo off
echo ==========================================
echo   AI Timetable Scheduler - Setup Script
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js is not installed or not in PATH
    echo Please install Node.js 16+ from https://nodejs.org/
    pause
    exit /b 1
)

echo [1/5] Setting up Backend...
cd backend

REM Remove old venv if exists
if exist venv (
    echo Removing old virtual environment...
    rmdir /s /q venv
)

REM Create new virtual environment
echo Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

REM Activate virtual environment and install dependencies
echo Installing Python dependencies (this may take a few minutes)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel
pip install fastapi==0.104.1
pip install uvicorn[standard]==0.24.0
pip install sqlalchemy==2.0.23
pip install pymysql==1.1.0
pip install python-jose[cryptography]==3.3.0
pip install passlib[bcrypt]==1.7.4
pip install python-multipart==0.0.6
pip install pydantic==2.5.0
pip install pydantic-settings==2.1.0
pip install python-dotenv==1.0.0
pip install alembic==1.13.0
pip install email-validator
pip install ortools==9.8.3296

if %errorlevel% neq 0 (
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)

echo Backend setup complete!
cd ..

echo.
echo [2/5] Setting up Frontend...
cd frontend

REM Install Node dependencies
echo Installing Node.js dependencies (this may take a few minutes)...
call npm install
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Node.js dependencies
    pause
    exit /b 1
)

echo Frontend setup complete!
cd ..

echo.
echo [3/5] Initializing Database...
cd backend
call venv\Scripts\activate.bat
python init_db.py
cd ..

echo.
echo [4/5] Setup Complete!
echo.
echo ==========================================
echo   Starting Servers...
echo ==========================================
echo.

REM Start backend in new window
echo [5/5] Starting Backend Server...
start "AI Timetable Backend" cmd /k "cd backend && venv\Scripts\activate.bat && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

REM Wait a bit for backend to start
timeout /t 3 /nobreak >nul

REM Start frontend in new window
echo Starting Frontend Server...
start "AI Timetable Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ==========================================
echo   Servers are starting!
echo ==========================================
echo.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo API Docs: http://localhost:8000/docs
echo.
echo Default Login:
echo   Username: admin
echo   Password: admin123
echo.
echo ==========================================
pause
