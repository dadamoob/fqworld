@echo off
REM ============================================================
REM  FQWorld - Installation en un double-clic (Windows)
REM ============================================================
title FQWorld - Installation
echo.
echo  ============================================
echo   FQWorld - Agent Twitch vers TikTok
echo  ============================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
    echo  [!] Docker Desktop n'est pas installe.
    echo      Une page de telechargement va s'ouvrir :
    echo      installez Docker Desktop, redemarrez le PC,
    echo      puis relancez ce fichier install.bat
    start https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
    echo  [!] Docker est installe mais pas demarre.
    echo      Lancez Docker Desktop (icone baleine), attendez
    echo      qu'il soit vert, puis relancez ce fichier.
    pause
    exit /b 1
)

echo  [1/2] Construction et demarrage de l'agent...
echo        (le premier lancement prend 2 a 5 minutes)
echo.
docker compose up --build -d
if errorlevel 1 (
    echo  [!] Une erreur est survenue. Copiez le message
    echo      ci-dessus pour obtenir de l'aide.
    pause
    exit /b 1
)

echo.
echo  [2/3] Creation des raccourcis sur le Bureau...
set "HERE=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop'); $s=$ws.CreateShortcut((Join-Path $d 'FQWorld.lnk')); $s.TargetPath='%HERE%FQWorld.bat'; $s.WorkingDirectory='%HERE%'; $s.Description='Lancer FQWorld (Twitch vers TikTok)'; $s.Save(); $s2=$ws.CreateShortcut((Join-Path $d 'Arreter FQWorld.lnk')); $s2.TargetPath='%HERE%stop.bat'; $s2.WorkingDirectory='%HERE%'; $s2.Description='Arreter FQWorld'; $s2.Save()" >nul 2>nul
if errorlevel 1 (
    echo      [i] Impossible de creer les raccourcis - vous pourrez
    echo          toujours double-cliquer sur FQWorld.bat dans ce dossier.
) else (
    echo      Raccourcis "FQWorld" et "Arreter FQWorld" crees sur le Bureau !
)

echo.
echo  [3/3] C'est pret ! Ouverture de l'interface...
echo.
echo   Au quotidien : double-cliquez sur le raccourci "FQWorld"
echo                  de votre Bureau (il demarre meme Docker si besoin)
echo   Interface    : http://localhost:8501
echo   Arreter      : raccourci "Arreter FQWorld" du Bureau
echo.
timeout /t 3 >nul
start http://localhost:8501
pause
