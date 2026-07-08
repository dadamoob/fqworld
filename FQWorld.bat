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
docker compose up -d
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
echo  C'est pret ! Ouverture dans votre navigateur...
start http://localhost:8501
timeout /t 2 >nul
exit /b 0
