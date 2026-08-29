@echo off
setlocal EnableDelayedExpansion

REM =======================================
REM   J.A.R.V.I.S - Unified Launcher
REM =======================================

color 0F

REM Navigate to project root (where this script lives)
cd /d "%~dp0"

REM Flags, scanned across every argument so the order does not matter.
REM   --logs     write logs\backend.log, logs\frontend.log and backend\logs\jarvis.log.
REM              Off by default: the directory used to reappear after every clean-up.
REM   --windows  give the backend and the frontend a console window each.
REM   --clean    drop the Next.js .next cache before starting.
REM By default both services stream into THIS terminal. `start /B` leaves them
REM attached to the console the script was launched from, so their output lands
REM where you are already looking and one Ctrl+C stops everything.
REM Two earlier defaults were worse: hidden processes with their output sent to
REM NUL left a backend that died on import with no trace anywhere, and the two
REM separate windows that replaced them moved every useful line out of the
REM terminal you were watching.
set "JARVIS_LOGS=0"
set "JARVIS_CLEAN=0"
set "JARVIS_WINDOWS=0"
echo.%* | findstr /i /c:"--logs" >nul && set "JARVIS_LOGS=1"
echo.%* | findstr /i /c:"--clean" >nul && set "JARVIS_CLEAN=1"
echo.%* | findstr /i /c:"--windows" >nul && set "JARVIS_WINDOWS=1"
if "%JARVIS_LOGS%"=="1" set "JARVIS_FILE_LOGGING=1"

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

REM Scrapling's stealth browser (Camoufox). Needed for Instagram, TikTok, Threads
REM and LinkedIn, which serve a wall to plain HTTP clients. The command is
REM idempotent and returns in under a second once installed, so it runs every
REM time rather than guessing at a marker file. If it fails, discovery still runs
REM on the HTTP tier and reports those platforms as "blocked" rather than
REM pretending nothing exists there.
echo [BACKEND] Checking stealth browser...
scrapling install
if %errorlevel% neq 0 (
    echo [WARN] Stealth browser unavailable - Instagram/TikTok/LinkedIn will report as blocked
) else (
    echo [OK] Stealth browser ready
)
echo.

REM Check .env file
if not exist ".env" (
    echo [WARNING] Backend .env file not found
    echo [INFO] Creating .env from .env.example...
    copy .env.example .env >nul
    echo [INFO] Please check backend\.env file for correct database credentials
)

REM Ensure data directory exists for SQLite
if not exist "data" (
    mkdir data
    echo [OK] Data directory created
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

REM Clean cache only when explicitly requested: start-jarvis.bat --clean
REM Keeping .next between runs avoids a full ~40s recompile on every start.
if "%JARVIS_CLEAN%"=="1" (
    if exist ".next" (
        echo [FRONTEND] Cleaning cache...
        rd /s /q ".next" >nul 2>&1
    )
)

cd ..

REM Ensure logs directory exists - only when --logs asked for one
if "%JARVIS_LOGS%"=="1" (
    if not exist "logs" mkdir logs
)

REM Kill any existing services
echo [INFO] Cleaning up any existing services...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 /nobreak >nul
echo.

echo [INFO] Starting Services...
echo [INFO] Backend: http://localhost:8000 ^| Frontend: http://localhost:3000 ^| Docs: http://localhost:8000/docs

REM Start Backend attached to this console unless a flag says otherwise
echo [BACKEND] Starting FastAPI server...
cd backend
call venv\Scripts\activate
set PYTHONPATH=%CD%
set PYTHONIOENCODING=utf-8
if "%JARVIS_LOGS%"=="1" goto backend_launch_logged
if "%JARVIS_WINDOWS%"=="1" goto backend_launch_window
REM /B: no new window, and stdout stays wired to the console you are reading.
start /B "" python -m app.main
goto backend_launched
:backend_launch_window
start "J.A.R.V.I.S Backend" cmd /k "python -m app.main"
goto backend_launched
:backend_launch_logged
start /B cmd /c "python -m app.main > ..\logs\backend.log 2>&1"
:backend_launched
cd ..
echo [OK] Backend started
echo.

REM Wait for backend — poll /health instead of a fixed sleep (max 60s)
echo [INFO] Waiting for backend to become ready...
set /a BACKEND_TRIES=0

:wait_backend
curl -s --max-time 5 http://localhost:8000/health >nul 2>&1
if %errorlevel% equ 0 goto backend_ready
set /a BACKEND_TRIES+=1
if %BACKEND_TRIES% geq 60 goto backend_timeout
timeout /t 1 /nobreak >nul
goto wait_backend

:backend_ready
echo [OK] Backend is running at http://localhost:8000
goto backend_done

:backend_timeout
echo [WARNING] Backend did not respond within 60 seconds
if "%JARVIS_LOGS%"=="1" goto backend_timeout_logs
if "%JARVIS_WINDOWS%"=="1" echo [INFO] Read the error in the "J.A.R.V.I.S Backend" window.
if not "%JARVIS_WINDOWS%"=="1" echo [INFO] The backend printed its error above, in this terminal.
echo.
goto backend_done
:backend_timeout_logs
echo [INFO] Checking logs\backend.log...
echo.
echo ======== BACKEND LOG (Last 20 lines) ========
powershell -NoProfile -Command "Get-Content logs\backend.log -Tail 20"
echo =============================================
echo.

:backend_done

REM Start Frontend attached to this console unless a flag says otherwise
echo [FRONTEND] Starting Next.js development server...
cd frontend
if "%JARVIS_LOGS%"=="1" goto frontend_launch_logged
if "%JARVIS_WINDOWS%"=="1" goto frontend_launch_window
start /B "" cmd /c "npm run dev"
goto frontend_launched
:frontend_launch_window
start "J.A.R.V.I.S Frontend" cmd /k "npm run dev"
goto frontend_launched
:frontend_launch_logged
start /B cmd /c "npm run dev > ..\logs\frontend.log 2>&1"
:frontend_launched
cd ..
echo [OK] Frontend started
echo.

REM Wait for frontend — poll until the page actually serves (max 180s).
REM Next.js dev needs ~20s to listen plus ~40s to compile the first page,
REM so a fixed 12s wait opened the browser on a dead port (ERR_CONNECTION_REFUSED).
echo [INFO] Waiting for frontend to become ready (first compile can take ~60s)...
set /a FRONTEND_TRIES=0

:wait_frontend
curl -s --max-time 120 http://localhost:3000 >nul 2>&1
if %errorlevel% equ 0 goto frontend_ready
set /a FRONTEND_TRIES+=1
if %FRONTEND_TRIES% geq 180 goto frontend_timeout
timeout /t 1 /nobreak >nul
goto wait_frontend

:frontend_ready
echo [OK] Frontend is running at http://localhost:3000
echo [INFO] Opening browser...
start http://localhost:3000
goto frontend_done

:frontend_timeout
echo [WARNING] Frontend did not respond within 180 seconds
if "%JARVIS_LOGS%"=="1" goto frontend_timeout_logs
if "%JARVIS_WINDOWS%"=="1" echo [INFO] Read the error in the "J.A.R.V.I.S Frontend" window.
if not "%JARVIS_WINDOWS%"=="1" echo [INFO] The frontend printed its error above, in this terminal.
echo.
goto frontend_timeout_done
:frontend_timeout_logs
echo [INFO] Checking logs\frontend.log...
echo.
echo ======== FRONTEND LOG (Last 20 lines) ========
powershell -NoProfile -Command "Get-Content logs\frontend.log -Tail 20"
echo =============================================
echo.
:frontend_timeout_done
echo [INFO] Not opening the browser — frontend is not serving yet.

:frontend_done

echo.
echo [INFO] J.A.R.V.I.S is now online.
if "%JARVIS_WINDOWS%"=="1" goto online_windows
if "%JARVIS_LOGS%"=="1" goto online_logs
echo [INFO] Backend and frontend stream into this terminal from here on.
echo [INFO] Press Ctrl+C or close this terminal to stop both services.
goto online_done
:online_windows
echo [INFO] Backend and frontend stream their output in their own windows.
echo [INFO] Close those two windows to stop the services, or re-run this script.
goto online_done
:online_logs
echo [INFO] Output goes to logs\backend.log and logs\frontend.log; the tail follows.
:online_done

REM Keep running; tail the logs only when there are logs to tail
:loop
timeout /t 5 /nobreak >nul
if not "%JARVIS_LOGS%"=="1" goto loop
REM Show last 3 lines of each log every 5 seconds
echo [%TIME%] Latest logs...
powershell -Command "$backend = Get-Content logs\backend.log -Tail 3 -ErrorAction SilentlyContinue; if($backend){Write-Host '[BACKEND]' -ForegroundColor Cyan; $backend}"
powershell -Command "$frontend = Get-Content logs\frontend.log -Tail 3 -ErrorAction SilentlyContinue; if($frontend){Write-Host '[FRONTEND]' -ForegroundColor Green; $frontend}"
goto loop
