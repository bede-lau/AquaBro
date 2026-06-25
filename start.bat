@echo off
setlocal
cd /d "%~dp0"
title AquaBro Launcher

echo ============================================================
echo  AquaBro start  ^>^>  postgres ^+ backend ^+ frontend
echo ============================================================

REM ---- .env (create from example on first run) ----
if not exist ".env" (
  echo [setup] copying .env.example -^> .env  ^(fill keys for full features^)
  copy ".env.example" ".env" >nul
)

REM ---- Postgres (Docker, detached) ----
echo [infra] starting postgres...
docker compose up -d postgres

REM ---- Python venv (create ^+ install on first run only) ----
if not exist ".venv\Scripts\activate.bat" (
  echo [setup] creating .venv ^+ installing backend deps ^(first run, slow^)...
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  pip install -q -r backend\requirements.txt
) else (
  call ".venv\Scripts\activate.bat"
)

REM ---- Frontend deps (install on first run only) ----
if not exist "frontend\node_modules" (
  echo [setup] installing frontend deps ^(first run, slow^)...
  pushd frontend
  call npm install --no-audit --no-fund
  popd
)

REM ---- Launch backend in its own window (UTF-8 for unicode logs) ----
echo [run] launching backend window...
start "AquaBro Backend" cmd /k "chcp 65001 >nul && cd /d "%~dp0" && call ".venv\Scripts\activate.bat" && python -m uvicorn app.main:app --reload --app-dir backend"

REM ---- Launch frontend in its own window ----
echo [run] launching frontend window...
start "AquaBro Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ============================================================
echo  AquaBro is up.
echo    Frontend : http://localhost:5173
echo    Backend  : http://localhost:8000   ^(docs: /docs^)
echo  Close the backend/frontend windows to stop them.
echo  Postgres keeps running in Docker (use stop.bat to tear down).
echo ============================================================
echo.
pause
endlocal
