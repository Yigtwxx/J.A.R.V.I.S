@echo off
setlocal EnableDelayedExpansion

REM =======================================
REM   J.A.R.V.I.S - Unified Launcher
REM =======================================

color 0B
mode con: cols=100 lines=30

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

REM Check if PostgreSQL is running
echo [SYSTEM CHECK] Checking PostgreSQL service...
sc query postgresql-x64-16 | find "RUNNING" >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] PostgreSQL service not found or not running
    echo [INFO] Please ensure PostgreSQL is installed and running
    echo.
)
echo [OK] PostgreSQL check complete
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
call npm install --silent
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install frontend dependencies
    pause
    exit /b 1
)
echo [OK] Frontend dependencies installed
echo.

cd ..

REM Start both services
echo.
echo ========================================================================
echo                       STARTING SERVICES
echo ========================================================================
echo.
echo [INFO] Backend URL: http://localhost:8000
echo [INFO] Backend Docs: http://localhost:8000/docs
echo [INFO] Frontend URL: http://localhost:3000
echo.
echo [INFO] Press Ctrl+C to stop both services
echo.
echo ========================================================================
echo.

REM Start backend in new window
start "J.A.R.V.I.S Backend" cmd /k "cd /d %~dp0backend && call venv\Scripts\activate && echo [BACKEND] Starting FastAPI server... && echo. && python app/main.py"

REM Wait for backend to start
timeout /t 3 /nobreak >nul

REM Start frontend in new window
start "J.A.R.V.I.S Frontend" cmd /k "cd /d %~dp0frontend && echo [FRONTEND] Starting Next.js development server... && echo. && npm run dev"

echo [OK] Both services started in separate windows
echo.
echo [INFO] Opening browser in 5 seconds...
timeout /t 5 /nobreak >nul

REM Open browser
start http://localhost:3000

echo.
echo [SUCCESS] J.A.R.V.I.S is now running!
echo.
echo Press any key to exit this launcher (services will continue running)...
pause >nul

exit /b 0
