@echo off
title MAPEZA ACADEMY - MACAD School Portal
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install requirements.
  pause
  exit /b 1
)
echo.
echo Starting MACAD School Portal...
echo Open Microsoft Edge and go to http://127.0.0.1:5000
echo Keep this window open while using the portal.
echo.
python app.py
pause
