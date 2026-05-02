@echo off
echo ========================================
echo   OSINT War Room - Starting...
echo ========================================
echo.

cd /d "%~dp0"

:: Check if Docker is running
docker info >nul 2>&1 || (echo [!] Docker Desktop is not running. Please start Docker Desktop first. & pause & exit /b 1)

:: Build and start
echo [*] Building and starting containers...
docker compose up -d --build || (echo [!] Failed to start. Check Docker Desktop is running. & pause & exit /b 1)

echo.
echo [*] Waiting for server to be ready...
timeout /t 3 /nobreak >nul

:: Open browser
echo [*] Opening dashboard...
start http://localhost:8000

echo.
echo ========================================
echo   War Room is LIVE at localhost:8000
echo   Press any key to close this window.
echo   (The server keeps running in Docker)
echo ========================================
pause >nul
