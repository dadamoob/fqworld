@echo off
REM ============================================================
REM  FQWorld - Mise a jour en un double-clic (Windows)
REM  Telecharge la derniere version et redemarre l'agent.
REM  Vos clips et votre configuration (dossier data\) sont conserves.
REM ============================================================
title FQWorld - Mise a jour
cd /d "%~dp0"
echo.
echo  Telechargement de la derniere version...
curl -L -s -o fqworld_new.zip https://codeload.github.com/dadamoob/fqworld/zip/refs/heads/main
if errorlevel 1 (
    echo  [!] Telechargement impossible. Verifiez votre connexion internet.
    pause
    exit /b 1
)

echo  Installation de la nouvelle version (data\ est conserve)...
tar -xf fqworld_new.zip
if errorlevel 1 (
    echo  [!] Extraction impossible.
    del fqworld_new.zip >nul 2>nul
    pause
    exit /b 1
)
xcopy /E /Y /Q fqworld-main\* . >nul
rmdir /S /Q fqworld-main
del fqworld_new.zip

echo  Reconstruction et redemarrage de l'agent...
if not exist "%~dp0data\clips" mkdir "%~dp0data\clips"
docker info >nul 2>nul
if errorlevel 1 (
    echo  [i] Docker n'est pas demarre : la nouvelle version sera
    echo      appliquee au prochain lancement via le raccourci FQWorld.
    pause
    exit /b 0
)
docker compose up --build -d
if errorlevel 1 (
    echo.
    echo  [!] La reconstruction a echoue (souvent un souci de connexion).
    echo      Les fichiers sont a jour : relancez FQWorld via le raccourci
    echo      du Bureau, il reessaiera automatiquement.
    pause
    exit /b 1
)
echo.
echo  Mise a jour terminee ! Rouvrez FQWorld via le raccourci du Bureau.
pause
