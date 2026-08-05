@echo off
REM FARTING-WHISPER — start tray app (no console)
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir logs
set PYW=%LocalAppData%\Programs\Python\Python311\pythonw.exe
if not exist "%PYW%" set PYW=pythonw
start "" "%PYW%" -u -m app.stt_app
exit /b 0
