#!/usr/bin/env bash
# ============================================================
#  FQWorld — Mise à jour en une commande (Mac / Linux)
#  Usage :  bash update.sh
#  Vos clips et votre configuration (dossier data/) sont conservés.
# ============================================================
set -e
cd "$(dirname "$0")"

echo ""
echo " Téléchargement de la dernière version…"
curl -L -s -o fqworld_new.zip https://codeload.github.com/dadamoob/fqworld/zip/refs/heads/main

echo " Installation de la nouvelle version (data/ est conservé)…"
unzip -o -q fqworld_new.zip
cp -R fqworld-main/. .
rm -rf fqworld-main fqworld_new.zip
chmod +x FQWorld.sh install.sh stop.sh update.sh 2>/dev/null || true

echo " Reconstruction et redémarrage de l'agent…"
if docker info >/dev/null 2>&1; then
    if docker compose up --build -d; then
        echo ""
        echo " Mise à jour terminée ! Rouvrez FQWorld via le raccourci du Bureau."
    else
        echo ""
        echo " [!] La reconstruction a échoué (souvent un souci de connexion)."
        echo "     Les fichiers sont à jour : relancez FQWorld via le raccourci"
        echo "     du Bureau, il réessaiera automatiquement."
    fi
else
    echo " [i] Docker n'est pas démarré : la nouvelle version sera appliquée"
    echo "     au prochain lancement via le raccourci FQWorld."
fi
