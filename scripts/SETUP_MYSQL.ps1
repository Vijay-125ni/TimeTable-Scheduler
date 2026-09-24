# AI Timetable Scheduler - Complete MySQL Setup Script
# This script sets up the project with MySQL database

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  AI Timetable Scheduler - MySQL Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    Write-Host "Running as Administrator - Enabling Long Paths..." -ForegroundColor Green
    try {
        Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name 'LongPathsEnabled' -Value 1 -ErrorAction Stop
        Write-Host "✓ Long paths enabled successfully!" -ForegroundColor Green
    } catch {
        Write-Host "⚠ Failed to enable long paths: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠ Not running as Administrator" -ForegroundColor Yellow
    Write-Host "  Long path support may not be enabled" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[1/7] Checking Prerequisites..." -ForegroundColor Cyan

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found. Please install Python 3.8+" -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    pause
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version 2>&1
    Write-Host "✓ Node.js found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Node.js not found. Please install Node.js 16+" -ForegroundColor Red
    Write-Host "  Download from: https://nodejs.org/" -ForegroundColor Yellow
    pause
    exit 1
}

# Check MySQL
$mysqlInstalled = $false
try {
    $mysqlVersion = mysql --version 2>&1
    Write-Host "✓ MySQL found: $mysqlVersion" -ForegroundColor Green
    $mysqlInstalled = $true
} catch {
    Write-Host "✗ MySQL not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "MySQL is REQUIRED for this project!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please install MySQL 8.0+ from:" -ForegroundColor Yellow
    Write-Host "  https://dev.mysql.com/downloads/installer/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Installation Steps:" -ForegroundColor Yellow
    Write-Host "  1. Download MySQL Installer" -ForegroundColor White
    Write-Host "  2. Choose 'Developer Default' setup" -ForegroundColor White
    Write-Host "  3. Set root password (remember this!)" -ForegroundColor White
    Write-Host "  4. Complete installation" -ForegroundColor White
    Write-Host "  5. Run this script again" -ForegroundColor White
    Write-Host ""
    pause
    exit 1
}

Write-Host ""
Write-Host "[2/7] MySQL Database Configuration..." -ForegroundColor Cyan

# Get MySQL credentials
Write-Host ""
Write-Host "Please provide MySQL credentials:" -ForegroundColor Yellow
$mysqlHost = Read-Host "MySQL Host (default: localhost)"
if ([string]::IsNullOrWhiteSpace($mysqlHost)) { $mysqlHost = "localhost" }

$mysqlPort = Read-Host "MySQL Port (default: 3306)"
if ([string]::IsNullOrWhiteSpace($mysqlPort)) { $mysqlPort = "3306" }

$mysqlUser = Read-Host "MySQL Username (default: root)"
if ([string]::IsNullOrWhiteSpace($mysqlUser)) { $mysqlUser = "root" }

$mysqlPassword = Read-Host "MySQL Password" -AsSecureString
$mysqlPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($mysqlPassword))

$dbName = "ai_timetable_scheduler"

Write-Host ""
Write-Host "Creating database '$dbName'..." -ForegroundColor Yellow

# Create database
$createDbScript = @"
CREATE DATABASE IF NOT EXISTS $dbName CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"@

try {
    $createDbScript | mysql -h $mysqlHost -P $mysqlPort -u $mysqlUser -p"$mysqlPasswordPlain" 2>&1
    Write-Host "✓ Database created successfully!" -ForegroundColor Green
} catch {
    Write-Host "⚠ Database creation warning (may already exist): $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[3/7] Setting up Backend..." -ForegroundColor Cyan
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
    Write-Host "✗ Failed to create virtual environment" -ForegroundColor Red
    Set-Location ".."
    pause
    exit 1
}

Write-Host "✓ Virtual environment created!" -ForegroundColor Green

# Update .env file with MySQL configuration
Write-Host "Configuring database connection..." -ForegroundColor Yellow
$databaseUrl = "mysql+pymysql://${mysqlUser}:${mysqlPasswordPlain}@${mysqlHost}:${mysqlPort}/${dbName}"
$envContent = @"
DATABASE_URL=$databaseUrl
SECRET_KEY=your-secret-key-change-this-in-production-$(Get-Random)
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3002,http://localhost:5173
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
DEBUG=True
"@

$envContent | Out-File -FilePath ".env" -Encoding UTF8
Write-Host "✓ Database configuration saved!" -ForegroundColor Green

# Activate and install
Write-Host ""
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
Write-Host "(This may take 5-10 minutes, please be patient)" -ForegroundColor Gray
Write-Host ""

& "venv\Scripts\Activate.ps1"

# Install packages with progress
$packages = @(
    @{Name="pip"; Version="latest"; Display="Package Manager"},
    @{Name="setuptools"; Version="latest"; Display="Build Tools"},
    @{Name="wheel"; Version="latest"; Display="Wheel Support"},
    @{Name="fastapi"; Version="0.104.1"; Display="FastAPI Framework"},
    @{Name="uvicorn[standard]"; Version="0.24.0"; Display="ASGI Server"},
    @{Name="sqlalchemy"; Version="2.0.23"; Display="Database ORM"},
    @{Name="pymysql"; Version="1.1.0"; Display="MySQL Connector"},
    @{Name="cryptography"; Version=""; Display="Cryptography"},
    @{Name="python-jose[cryptography]"; Version="3.3.0"; Display="JWT Authentication"},
    @{Name="passlib[bcrypt]"; Version="1.7.4"; Display="Password Hashing"},
    @{Name="python-multipart"; Version="0.0.6"; Display="Form Data"},
    @{Name="pydantic"; Version="2.5.0"; Display="Data Validation"},
    @{Name="pydantic-settings"; Version="2.1.0"; Display="Settings Management"},
    @{Name="python-dotenv"; Version="1.0.0"; Display="Environment Variables"},
    @{Name="alembic"; Version="1.13.0"; Display="Database Migrations"},
    @{Name="email-validator"; Version=""; Display="Email Validation"},
    @{Name="numpy"; Version=""; Display="Numerical Computing"},
    @{Name="pandas"; Version=""; Display="Data Analysis"},
    @{Name="ortools"; Version="9.8.3296"; Display="Optimization Solver"}
)

$total = $packages.Count
$current = 0

foreach ($pkg in $packages) {
    $current++
    $pkgSpec = if ($pkg.Version) { "$($pkg.Name)==$($pkg.Version)" } else { $pkg.Name }
    
    Write-Host "[$current/$total] Installing $($pkg.Display)..." -ForegroundColor Cyan
    
    & "venv\Scripts\pip.exe" install --no-cache-dir --prefer-binary $pkgSpec 2>&1 | Out-Null
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ $($pkg.Display) installed" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ $($pkg.Display) installation had issues (may still work)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "✓ Backend dependencies installed!" -ForegroundColor Green
Set-Location ".."

Write-Host ""
Write-Host "[4/7] Setting up Frontend..." -ForegroundColor Cyan
Set-Location "frontend"

Write-Host "Installing Node.js dependencies..." -ForegroundColor Yellow
npm install 2>&1 | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Frontend dependencies installed!" -ForegroundColor Green
} else {
    Write-Host "⚠ Frontend installation had issues" -ForegroundColor Yellow
}

Set-Location ".."

Write-Host ""
Write-Host "[5/7] Initializing Database Schema..." -ForegroundColor Cyan
Set-Location "backend"
& "venv\Scripts\Activate.ps1"

Write-Host "Creating database tables and initial data..." -ForegroundColor Yellow
python init_db.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Database initialized successfully!" -ForegroundColor Green
} else {
    Write-Host "⚠ Database initialization had issues" -ForegroundColor Yellow
}

Set-Location ".."

Write-Host ""
Write-Host "[6/7] Verifying Installation..." -ForegroundColor Cyan

# Test imports
Set-Location "backend"
& "venv\Scripts\Activate.ps1"

$testScript = @"
try:
    import fastapi
    import uvicorn
    import sqlalchemy
    import pymysql
    from ortools.sat.python import cp_model
    print('✓ All critical packages imported successfully!')
except ImportError as e:
    print(f'⚠ Import error: {e}')
"@

$testScript | python 2>&1

Set-Location ".."

Write-Host ""
Write-Host "[7/7] Setup Complete!" -ForegroundColor Green
Write-Host ""

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Starting Servers..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Start backend
Write-Host "Starting Backend Server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'backend'; .\venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

# Wait for backend
Start-Sleep -Seconds 5

# Start frontend
Write-Host "Starting Frontend Server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'frontend'; npm run dev"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access Points:" -ForegroundColor Yellow
Write-Host "  Frontend:  http://localhost:5173" -ForegroundColor White
Write-Host "  Backend:   http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs:  http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Database:" -ForegroundColor Yellow
Write-Host "  Type:      MySQL" -ForegroundColor White
Write-Host "  Database:  $dbName" -ForegroundColor White
Write-Host "  Host:      $mysqlHost:$mysqlPort" -ForegroundColor White
Write-Host ""
Write-Host "Default Login:" -ForegroundColor Yellow
Write-Host "  Username:  admin" -ForegroundColor White
Write-Host "  Password:  admin123" -ForegroundColor White
Write-Host ""
Write-Host "⚠ IMPORTANT: Change the admin password after first login!" -ForegroundColor Red
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press any key to exit this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
