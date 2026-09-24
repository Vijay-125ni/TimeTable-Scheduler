# AI Timetable Scheduler - Complete Setup Script
# This script will enable long paths, install dependencies, and start the servers

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  AI Timetable Scheduler - Setup Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "WARNING: Not running as Administrator" -ForegroundColor Yellow
    Write-Host "Attempting to enable long paths requires Administrator privileges" -ForegroundColor Yellow
    Write-Host "The script will continue, but may fail if long paths are not enabled" -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne 'y') {
        exit
    }
} else {
    Write-Host "Enabling Windows Long Path Support..." -ForegroundColor Green
    try {
        Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name 'LongPathsEnabled' -Value 1 -ErrorAction Stop
        Write-Host "Long paths enabled successfully!" -ForegroundColor Green
    } catch {
        Write-Host "Failed to enable long paths: $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "[1/6] Checking Prerequisites..." -ForegroundColor Cyan

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found. Please install Python 3.8+" -ForegroundColor Red
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version 2>&1
    Write-Host "✓ Node.js found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Node.js not found. Please install Node.js 16+" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[2/6] Setting up Backend..." -ForegroundColor Cyan
Set-Location "backend"

# Remove old venv
if (Test-Path "venv") {
    Write-Host "Removing old virtual environment..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "venv" -ErrorAction SilentlyContinue
}

# Create venv
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
python -m venv venv
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to create virtual environment" -ForegroundColor Red
    exit 1
}

# Activate and install
Write-Host "Installing Python dependencies (this may take several minutes)..." -ForegroundColor Yellow
& "venv\Scripts\Activate.ps1"

# Install packages one by one to avoid path issues
$packages = @(
    "fastapi==0.104.1",
    "uvicorn[standard]==0.24.0",
    "sqlalchemy==2.0.23",
    "pymysql==1.1.0",
    "python-jose==3.3.0",
    "cryptography",
    "bcrypt",
    "passlib",
    "pydantic-settings",
    "alembic",
    "email-validator",
    "numpy",
    "pandas",
    "protobuf",
    "absl-py",
    "ortools"
)

foreach ($package in $packages) {
    Write-Host "Installing $package..." -ForegroundColor Gray
    & "venv\Scripts\pip.exe" install --no-cache-dir $package
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Warning: Failed to install $package" -ForegroundColor Yellow
    }
}

Write-Host "✓ Backend setup complete!" -ForegroundColor Green
Set-Location ".."

Write-Host ""
Write-Host "[3/6] Setting up Frontend..." -ForegroundColor Cyan
Set-Location "frontend"

Write-Host "Installing Node.js dependencies..." -ForegroundColor Yellow
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install Node.js dependencies" -ForegroundColor Red
    Set-Location ".."
    exit 1
}

Write-Host "✓ Frontend setup complete!" -ForegroundColor Green
Set-Location ".."

Write-Host ""
Write-Host "[4/6] Initializing Database..." -ForegroundColor Cyan
Set-Location "backend"
& "venv\Scripts\Activate.ps1"
python init_db.py
Set-Location ".."

Write-Host ""
Write-Host "[5/6] Setup Complete!" -ForegroundColor Green
Write-Host ""

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Starting Servers..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Start backend
Write-Host "[6/6] Starting Backend Server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'backend'; .\venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

# Wait for backend
Start-Sleep -Seconds 3

# Start frontend
Write-Host "Starting Frontend Server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'frontend'; npm run dev"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Servers are starting!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "Frontend: http://localhost:5173" -ForegroundColor White
Write-Host "API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Default Login:" -ForegroundColor Yellow
Write-Host "  Username: admin" -ForegroundColor White
Write-Host "  Password: admin123" -ForegroundColor White
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press any key to exit this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
