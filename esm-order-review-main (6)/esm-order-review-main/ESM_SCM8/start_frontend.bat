@echo off
setlocal

cd /d "%~dp0frontend"

echo Starting ESM SCM Next.js frontend...
echo Project: %CD%
echo URL: http://127.0.0.1:3000
echo.

if not exist "node_modules" (
  echo node_modules not found. Installing frontend dependencies...
  call npm.cmd install
  if errorlevel 1 (
    echo.
    echo npm install failed.
    pause
    exit /b 1
  )
  echo.
)

call npm.cmd run dev

echo.
echo Frontend server stopped.
pause
