@echo off
setlocal
if "%~1"=="" goto :usage
if "%~2"=="" goto :usage
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" (
 echo Microsoft Edge was not found. Open the output URL in an installed browser.
 exit /b 1
)
"%EDGE%" --kiosk "http://%~1:8765/led_displays/?screen=%~2" --edge-kiosk-type=fullscreen --no-first-run
exit /b 0
:usage
echo Usage: OPEN_LED_PLAYER.cmd SERVER_PRIVATE_IP master
echo Screen keys: master l1 l2 screen2 screen3 stage
exit /b 1
