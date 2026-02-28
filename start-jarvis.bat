@echo off
setlocal EnableDelayedExpansion

REM =======================================
REM   J.A.R.V.I.S - Unified Launcher
REM =======================================

color 0F

echo.
echo     ========================================================================
echo                          J.A.R.V.I.S AI Assistant
echo              Just A Rather Very Intelligent System - Starting...
echo     ========================================================================

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

echo [SETUP] Initializing Backend...

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

echo [BACKEND] Upgrading pip...
python -m pip install -q --upgrade pip
echo [OK] Pip upgraded
echo.

echo [BACKEND] Installing dependencies...
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install backend dependencies
    cd ..
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
    echo [INFO] Please check backend\.env file for correct database credentials
)

cd ..

echo [SETUP] Initializing Frontend...

cd frontend

echo [FRONTEND] Installing dependencies...
call npm install --silent
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install frontend dependencies
    cd ..
    pause
    exit /b 1
)
echo [OK] Frontend dependencies installed
echo.

REM Clean cache
if exist ".next" (
    echo [FRONTEND] Cleaning cache...
    rd /s /q ".next" >nul 2>&1
)

cd ..

REM Kill any existing services
echo [INFO] Cleaning up any existing services...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 /nobreak >nul
echo.

echo [INFO] Starting Services...
echo [INFO] Backend: http://localhost:8000 ^| Frontend: http://localhost:3000 ^| Docs: http://localhost:8000/docs

REM Start Backend in background (no window)
echo [BACKEND] Starting FastAPI server...
cd backend
call venv\Scripts\activate
set PYTHONPATH=%CD%
start /B cmd /c "python -m app.main > ..\logs\backend.log 2>&1"
cd ..
echo [OK] Backend started in background
echo.

REM Wait for backend
echo [INFO] Waiting for backend to initialize (8 seconds)...
timeout /t 8 /nobreak >nul

REM Check backend
curl -s http://localhost:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend is running at http://localhost:8000
) else (
    echo [WARNING] Backend not responding
    echo [INFO] Checking logs\backend.log...
    echo.
    echo ======== BACKEND LOG (Last 10 lines) ========
    powershell -Command "Get-Content logs\backend.log -Tail 10"
    echo =============================================
    echo.
)

REM Start Frontend in background (no window)
echo [FRONTEND] Starting Next.js development server...
cd frontend
start /B cmd /c "npm run dev > ..\logs\frontend.log 2>&1"
cd ..
echo [OK] Frontend started in background
echo.

REM Wait for frontend
echo [INFO] Waiting for frontend to initialize (12 seconds)...
timeout /t 12 /nobreak >nul

REM Check frontend
curl -s http://localhost:3000 >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Frontend is running at http://localhost:3000
) else (
    echo [WARNING] Frontend not responding
    echo [INFO] Checking logs\frontend.log...
    echo.
    echo ======== FRONTEND LOG (Last 10 lines) ========
    powershell -Command "Get-Content logs\frontend.log -Tail 10"
    echo =============================================
    echo.
)

echo.
echo [INFO] Opening browser in 3 seconds...
timeout /t 3 /nobreak >nul
start http://localhost:3000

echo.
echo [INFO] J.A.R.V.I.S is now online.
echo [INFO] Press Ctrl+C to stop all services and exit.

REM Keep running and watch logs
:loop
timeout /t 5 /nobreak >nul
REM Show last 3 lines of each log every 5 seconds
echo [%TIME%] Latest logs...
powershell -Command "$backend = Get-Content logs\backend.log -Tail 3 -ErrorAction SilentlyContinue; if($backend){Write-Host '[BACKEND]' -ForegroundColor Cyan; $backend}"
powershell -Command "$frontend = Get-Content logs\frontend.log -Tail 3 -ErrorAction SilentlyContinue; if($frontend){Write-Host '[FRONTEND]' -ForegroundColor Green; $frontend}"
goto loop
