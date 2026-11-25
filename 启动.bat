@echo off
chcp 65001 >nul
title Live Photo Factory
cd /d "%~dp0"

set "PYTHONPATH="
set "PYTHONIOENCODING=utf-8"

set "PYEXE="
if exist "C:\Program Files\python\python.exe" set "PYEXE=C:\Program Files\python\python.exe"
if not defined PYEXE if exist "C:\Python38\python.exe" set "PYEXE=C:\Python38\python.exe"
if not defined PYEXE for /f "delims=" %%i in ('where python 2^>nul') do if not defined PYEXE set "PYEXE=%%i"

if not defined PYEXE (
  echo.
  echo   Python not found. Install Python 3.8+ first.
  echo.
  pause
  exit /b 1
)

echo.
echo   Starting on http://127.0.0.1:8770 ...
echo   Press Ctrl+C to stop.
echo.

"%PYEXE%" -S "%~dp0run.py" %*

echo.
echo   Server stopped.
pause
