@echo off
REM ============================================================
REM  FQWorld - Lanceur quotidien (c'est lui que vise le
REM  raccourci Bureau cree par install.bat)
REM ============================================================
title FQWorld
cd /d "%~dp0"

docker info >nul 2>nul
if not errorlevel 1 goto ready

echo  Docker n'est pas demarre. Lancement de Docker Desktop...
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" 2>nul
echo  Patientez (jusqu'a 60 secondes)...
for /l %%i in (1,1,30) do (
    docker info >nul 2>nul && goto ready
    timeout /t 2 >nul
)
echo.
echo  [!] Docker n'a pas demarre. Ouvrez Docker Desktop manuellement
echo      (icone baleine) puis relancez FQWorld.
pause
exit /b 1

:ready
echo  Demarrage de FQWorld...
REM --build : applique automatiquement une mise a jour telechargee
REM (instantane si rien n'a change, grace au cache Docker)
docker compose up -d --build
echo  Attente de l'interface (quelques secondes)...
for /l %%i in (1,1,60) do (
    curl -s -o nul http://localhost:8501 2>nul && goto open
    timeout /t 2 >nul
)
echo.
echo  [!] L'interface met du temps a demarrer. Ouvrez (ou actualisez)
echo      cette page dans votre navigateur : http://localhost:8501
pause
exit /b 1

:open
echo  C'est pret ! Ouverture de FQWorld...
REM Fenetre applicative dediee (comme un vrai logiciel) via Edge ou Chrome
set "APPBROWSER="
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "APPBROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "APPBROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "APPBROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "APPBROWSER=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if defined APPBROWSER (
    start "" "%APPBROWSER%" --app=http://localhost:8501 --window-size=1320,920
) else (
    start http://localhost:8501
)
timeout /t 2 >nul
exit /b 0
