@echo off
echo ========================================
echo   OSINT War Room - Share Anywhere
echo ========================================
echo.

cd /d "%~dp0"

:: Check if container is running
docker inspect osint-warroom >nul 2>&1 || (echo [!] War Room is not running. Run start.bat first. & pause & exit /b 1)

:: Check if cloudflared is installed
where cloudflared >nul 2>&1 || goto :install_cf

:: Get local IP
set "LOCAL_IP="
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127.0.0.1"') do set "LOCAL_IP=%%a" & goto :got_ip
:got_ip
if defined LOCAL_IP set "LOCAL_IP=%LOCAL_IP: =%"

:: Start tunnel in background, capture output to log file
set "CF_LOG=%TEMP%\cf_tunnel.log"
del "%CF_LOG%" 2>nul
echo [*] Connecting to Cloudflare...
start "" /b cmd /c "cloudflared tunnel --url http://localhost:8000 > %CF_LOG% 2>&1"

:: Wait for URL to appear (up to 30 seconds)
set /a TRIES=0
:wait_url
timeout /t 1 /nobreak >nul
set /a TRIES+=1
findstr /r "https.*trycloudflare" "%CF_LOG%" >nul 2>&1 && goto :found_url
if %TRIES% lss 30 goto :wait_url
echo [!] Timed out waiting for tunnel URL.
pause
goto :eof

:found_url
:: Extract URL — 4th space-delimited token from the line with https + trycloudflare
set "TUNNEL_URL="
for /f "tokens=4" %%u in ('findstr /c:"https:" "%CF_LOG%" ^| findstr "trycloudflare"') do set "TUNNEL_URL=%%u"
if not defined TUNNEL_URL (echo [!] Could not extract tunnel URL. & pause & goto :eof)
echo.
echo ========================================
echo.
echo   PUBLIC URL:  %TUNNEL_URL%
echo.
if defined LOCAL_IP echo   LAN:         http://%LOCAL_IP%:8000
echo   Local:       http://localhost:8000
echo.
echo ========================================
echo.
echo   Share the link above with anyone.
echo   Press any key to stop sharing...
echo.
pause >nul
taskkill /f /im cloudflared.exe >nul 2>&1
del "%CF_LOG%" 2>nul
goto :eof

:install_cf
echo [*] cloudflared not found. Installing via winget...
winget install --id Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements || (echo [!] Failed to install cloudflared. & pause & exit /b 1)
echo.
echo [*] cloudflared installed. Close this window and re-run share.bat
echo     (the new install needs a fresh window to be found)
pause
