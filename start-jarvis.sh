#!/bin/bash

# =======================================
#   J.A.R.V.I.S - Unified Launcher
#   macOS/Linux Version
# =======================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "    ========================================================================"
echo "                         J.A.R.V.I.S AI Assistant"
echo "             Just A Rather Very Intelligent System - Starting..."
echo "    ========================================================================"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if Ollama is running
echo -e "${CYAN}[SYSTEM CHECK]${NC} Checking Ollama service..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${RED}[WARNING]${NC} Ollama is not running! Please start Ollama first."
    echo -e "${YELLOW}[INFO]${NC} Download from: https://ollama.ai/download"
    echo ""
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Ollama is running"
echo ""

# Setup Backend
echo "========================================================================"
echo "                         BACKEND SETUP"
echo "========================================================================"
echo ""

cd backend

echo -e "${CYAN}[BACKEND]${NC} Checking virtual environment..."
if [ ! -d "venv" ]; then
    echo -e "${CYAN}[BACKEND]${NC} Creating virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}[OK]${NC} Virtual environment created"
else
    echo -e "${GREEN}[OK]${NC} Virtual environment exists"
fi
echo ""

echo -e "${CYAN}[BACKEND]${NC} Activating virtual environment..."
source venv/bin/activate

echo -e "${CYAN}[BACKEND]${NC} Upgrading pip..."
python -m pip install -q --upgrade pip
echo -e "${GREEN}[OK]${NC} Pip upgraded"
echo ""

echo -e "${CYAN}[BACKEND]${NC} Installing dependencies..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR]${NC} Failed to install backend dependencies"
    cd ..
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Backend dependencies installed"
echo ""

# Check .env file
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}[WARNING]${NC} Backend .env file not found"
    echo -e "${YELLOW}[INFO]${NC} Creating .env from .env.example..."
    cp .env.example .env
    echo -e "${YELLOW}[INFO]${NC} Please check backend/.env file for correct database credentials"
fi

cd ..

# Setup Frontend
echo "========================================================================"
echo "                         FRONTEND SETUP"
echo "========================================================================"
echo ""

cd frontend

echo -e "${CYAN}[FRONTEND]${NC} Installing dependencies..."
npm install --silent
if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR]${NC} Failed to install frontend dependencies"
    cd ..
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Frontend dependencies installed"
echo ""

# Clean cache
if [ -d ".next" ]; then
    echo -e "${CYAN}[FRONTEND]${NC} Cleaning cache..."
    rm -rf .next
fi

cd ..

# Kill any existing services
echo -e "${YELLOW}[INFO]${NC} Cleaning up any existing services..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null
sleep 2
echo ""

echo "========================================================================"
echo "                      STARTING SERVICES"
echo "========================================================================"
echo ""
echo -e "${YELLOW}[INFO]${NC} Backend: http://localhost:8000"
echo -e "${YELLOW}[INFO]${NC} Frontend: http://localhost:3000"
echo -e "${YELLOW}[INFO]${NC} API Docs: http://localhost:8000/docs"
echo ""
echo "========================================================================"
echo ""

# Start Backend in background
echo -e "${CYAN}[BACKEND]${NC} Starting FastAPI server..."
cd backend
source venv/bin/activate
export PYTHONPATH="$PWD"
python -m app.main > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
cd ..
echo -e "${GREEN}[OK]${NC} Backend started in background (PID: $BACKEND_PID)"
echo ""

# Wait for backend
echo -e "${YELLOW}[INFO]${NC} Waiting for backend to initialize (8 seconds)..."
sleep 8

# Check backend
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} Backend is running at http://localhost:8000"
else
    echo -e "${YELLOW}[WARNING]${NC} Backend not responding"
    echo -e "${YELLOW}[INFO]${NC} Checking backend.log..."
    echo ""
    echo "======== BACKEND LOG (Last 10 lines) ========"
    tail -10 logs/backend.log
    echo "============================================="
    echo ""
fi

# Start Frontend in background
echo -e "${CYAN}[FRONTEND]${NC} Starting Next.js development server..."
cd frontend
npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..
echo -e "${GREEN}[OK]${NC} Frontend started in background (PID: $FRONTEND_PID)"
echo ""

# Wait for frontend
echo -e "${YELLOW}[INFO]${NC} Waiting for frontend to initialize (12 seconds)..."
sleep 12

# Check frontend
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} Frontend is running at http://localhost:3000"
else
    echo -e "${YELLOW}[WARNING]${NC} Frontend not responding"
    echo -e "${YELLOW}[INFO]${NC} Checking frontend.log..."
    echo ""
    echo "======== FRONTEND LOG (Last 10 lines) ========"
    tail -10 logs/frontend.log
    echo "============================================="
    echo ""
fi

echo ""
echo -e "${YELLOW}[INFO]${NC} Opening browser in 3 seconds..."
sleep 3

# Open browser (macOS uses 'open', Linux uses 'xdg-open')
if [[ "$OSTYPE" == "darwin"* ]]; then
    open http://localhost:3000
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open http://localhost:3000 2>/dev/null || echo "Please open http://localhost:3000 manually"
fi

echo ""
echo "========================================================================"
echo "  J.A.R.V.I.S is now running!"
echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "  View real-time logs:"
echo "  - tail -f logs/backend.log"
echo "  - tail -f logs/frontend.log"
echo ""
echo "  Press Ctrl+C to stop all services and exit"
echo "========================================================================"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}[INFO]${NC} Stopping services..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}[OK]${NC} Services stopped. Goodbye!"
    exit 0
}

# Trap Ctrl+C
trap cleanup SIGINT SIGTERM

# Keep running and watch logs
while true; do
    sleep 5
    echo "[$(date +%H:%M:%S)] Latest logs..."
    echo -e "${CYAN}[BACKEND]${NC}"
    tail -3 logs/backend.log 2>/dev/null
    echo -e "${GREEN}[FRONTEND]${NC}"
    tail -3 logs/frontend.log 2>/dev/null
done
