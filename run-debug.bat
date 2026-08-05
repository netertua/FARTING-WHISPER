@echo off
REM FARTING-WHISPER — console debug mode
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir logs
set PY=%LocalAppData%\Programs\Python\Python311\python.exe
if not exist "%PY%" set PY=python
echo === FARTING-WHISPER DEBUG ===
"%PY%" -u -m app.stt_app
echo Exit %ERRORLEVEL%
pause
