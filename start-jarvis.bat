@echo off
setlocal EnableDelayedExpansion

REM =======================================
REM   J.A.R.V.I.S - Unified Launcher
REM =======================================

color 0B

echo.
echo     ========================================================================
echo                          J.A.R.V.I.S AI Assistant
echo              Just A Rather Very Intelligent System - Starting...
echo     ========================================================================
echo.

REM Check if Ollama is running
echo [SYSTEM CHECK] Checking Ollama service...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Ollama is not running! Please start Ollama first.
    echo [INFO] Download from: https://ollama.ai/download
    echo.
    pause
    exit /b 1
)
echo [OK] Ollama is running
echo.

REM Setup Backend
echo ========================================================================
echo                          BACKEND SETUP
echo ========================================================================
echo.

cd backend

echo [BACKEND] Checking virtual environment...
if not exist "venv" (
    echo [BACKEND] Creating virtual environment...
    python -m venv venv
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment exists
)
echo.

echo [BACKEND] Activating virtual environment...
call venv\Scripts\activate
echo [OK] Virtual environment activated
echo.

echo [BACKEND] Upgrading pip...
python -m pip install -q --upgrade pip >nul 2>&1
echo [OK] Pip upgraded
echo.

echo [BACKEND] Installing dependencies...
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install backend dependencies
    pause
    exit /b 1
)
echo [OK] Backend dependencies installed
echo.

REM Check .env file
if not exist ".env" (
    echo [WARNING] Backend .env file not found
    echo [INFO] Creating .env from .env.example...
    copy .env.example .env >nul
    echo [INFO] Please edit backend\.env with your database credentials
    echo.
)

cd ..

REM Setup Frontend
echo ========================================================================
echo                          FRONTEND SETUP
echo ========================================================================
echo.

cd frontend

echo [FRONTEND] Installing dependencies...
call npm install --silent >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install frontend dependencies
    pause
    exit /b 1
)
echo [OK] Frontend dependencies installed
echo.

cd ..

REM Start services in background
echo.
echo ========================================================================
echo                       STARTING SERVICES
echo ========================================================================
echo.
echo [INFO] Backend URL: http://localhost:8000
echo [INFO] Backend Docs: http://localhost:8000/docs
echo [INFO] Frontend URL: http://localhost:3000
echo.
echo ========================================================================
echo.

REM Kill any existing services on these ports
echo [INFO] Cleaning up any existing services...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 /nobreak >nul
echo [OK] Cleanup complete
echo.

REM Start backend in background
echo [BACKEND] Starting FastAPI server...
cd backend
start /B cmd /c "call venv\Scripts\activate && set PYTHONPATH=. && python app\main.py > ..\backend.log 2>&1"
cd ..

REM Wait for backend
echo [INFO] Waiting for backend to start...
timeout /t 8 /nobreak >nul

REM Start frontend in background
echo [FRONTEND] Starting Next.js development server...
cd frontend
if exist ".next" (
    rd /s /q ".next" >nul 2>&1
)
start /B cmd /c "npm run dev > ..\frontend.log 2>&1"
cd ..

REM Wait for services
echo [INFO] Waiting for services to initialize...
timeout /t 15 /nobreak >nul

echo.
echo [SUCCESS] Services are starting up!
echo.

REM Check services
echo [INFO] Checking services...
curl -s http://localhost:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend is running at http://localhost:8000
) else (
    echo [WARNING] Backend may still be starting up...
    echo [INFO] Check backend.log for details
)

curl -s http://localhost:3000 >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Frontend is running at http://localhost:3000
) else (
    echo [INFO] Frontend is still starting up...
    echo [INFO] Check frontend.log for details
)

echo.
echo [INFO] Opening browser in 3 seconds...
timeout /t 3 /nobreak >nul
start http://localhost:3000

echo.
echo ========================================================================
echo   J.A.R.V.I.S is now running!
echo.
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000  
echo   API Docs: http://localhost:8000/docs
echo.
echo   View logs:
echo   - backend.log (Backend output)
echo   - frontend.log (Frontend output)
echo.
echo   Press Ctrl+C to stop all services
echo ========================================================================
echo.

REM Keep running
:loop
timeout /t 60 /nobreak >nul
goto loop
