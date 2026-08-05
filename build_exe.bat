@echo off
setlocal
cd /d "%~dp0"
set PY=%LocalAppData%\Programs\Python\Python311\python.exe
if not exist "%PY%" set PY=python
set OUT=%USERPROFILE%\Desktop\FARTING-WHISPER-build

echo [FW] deps...
"%PY%" -m pip install -q -r requirements.txt pyinstaller keyboard

echo [FW] clean...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [FW] PyInstaller...
"%PY%" -m PyInstaller --noconfirm --clean pc_wide_stt.spec
if errorlevel 1 exit /b 1

echo [FW] stage to Desktop\FARTING-WHISPER-build ...
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"
xcopy /e /i /y /q "dist\FARTING-WHISPER\*" "%OUT%\"
copy /y config-grok-build.json "%OUT%\" >nul
copy /y config.json "%OUT%\" >nul
copy /y VERSION.txt "%OUT%\" >nul
copy /y LICENSE "%OUT%\" >nul
copy /y README.md "%OUT%\" >nul
if not exist "%OUT%\model\kroko-tr-128l" (
  mkdir "%OUT%\model\kroko-tr-128l"
  xcopy /e /i /y /q "model\kroko-tr-128l\*" "%OUT%\model\kroko-tr-128l\"
)
(
  echo @echo off
  echo cd /d "%%~dp0"
  echo start "" "%%~dp0FARTING-WHISPER.exe"
) > "%OUT%\Start-FARTING-WHISPER.bat"

echo [FW] OK -^> %OUT%
dir "%OUT%\FARTING-WHISPER.exe"
exit /b 0
