@echo off
title FQWorld - Assemblage du logiciel
echo.
echo  Assemblage de FQWorld.exe (quelques secondes)...
copy /b FQWorld.exe.part00+FQWorld.exe.part01 FQWorld.exe >nul
if exist FQWorld.exe (
    del FQWorld.exe.part00 FQWorld.exe.part01
    echo.
    echo  C'est pret ! Double-cliquez maintenant sur FQWorld.exe
    echo  (si SmartScreen s'affiche : "Informations complementaires"
    echo   puis "Executer quand meme")
) else (
    echo  [!] Echec de l'assemblage.
)
echo.
pause
