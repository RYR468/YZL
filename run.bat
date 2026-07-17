@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Port 5000 already listening? Open browser only, avoid double launch.
netstat -ano | findstr "LISTENING" | findstr ":5000 " >nul
if not errorlevel 1 (
  echo Already running - opening browser...
  start "" http://127.0.0.1:5000
  timeout /t 2 >nul
  exit /b
)

echo ========================================
echo   YiZhiLing Mentor Matching - starting...
echo   Browser opens automatically. Keep this window open.
echo   To stop: close this window.
echo ========================================
python app.py
if errorlevel 1 (
  echo.
  echo Startup failed - see error above.
)
echo.
echo Service stopped. Press any key to close...
pause >nul
