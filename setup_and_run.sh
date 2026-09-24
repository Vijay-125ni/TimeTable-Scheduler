#!/usr/bin/env bash

# Setup and run script for Linux

echo "=========================================="
echo "  AI Timetable Scheduler - Setup Script"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python is not installed or not in PATH"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js is not installed or not in PATH"
    exit 1
fi

echo "[1/4] Setting up Backend..."
cd backend || exit

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment and install dependencies
echo "Installing Python dependencies (this may take a few minutes)..."
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt


echo "Backend setup complete!"
cd ..

echo ""
echo "[2/4] Setting up Frontend..."
cd frontend || exit

# Install Node dependencies
echo "Installing Node.js dependencies (this may take a few minutes)..."
npm install

echo "Frontend setup complete!"
cd ..

echo ""
echo "[3/4] Setup Complete!"
echo ""
echo "=========================================="
echo "  Starting Servers..."
echo "=========================================="
echo ""

echo "[4/4] Starting Backend Server..."
cd backend || exit
source venv/bin/activate
nohup python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
BACKEND_PID=$!
cd ..

echo "Starting Frontend Server..."
cd frontend || exit
nohup npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo ""
echo "=========================================="
echo "  Servers are starting in the background!"
echo "=========================================="
echo ""
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3002"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "You can view logs at:"
echo "- ./backend.log"
echo "- ./frontend.log"
echo ""
echo "To stop the servers later, run:"
echo "kill $BACKEND_PID $FRONTEND_PID"
echo "=========================================="
echo "Setup and Run Script Finished successfully."
