@echo off
echo Stopping AquaBro...
taskkill /FI "WINDOWTITLE eq AquaBro Backend*"   /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AquaBro Frontend*"  /T /F >nul 2>&1
docker compose down >nul 2>&1
echo Done. (backend, frontend windows closed; postgres container stopped)
pause
