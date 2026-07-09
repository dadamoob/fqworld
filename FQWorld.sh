#!/usr/bin/env bash
# ============================================================
#  FQWorld — Lanceur quotidien (c'est lui que vise le
#  raccourci Bureau créé par install.sh)
# ============================================================
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
    if [ -d "/Applications/Docker.app" ]; then
        echo " Docker n'est pas démarré. Lancement de Docker Desktop…"
        open -a Docker
        for _ in $(seq 1 30); do
            docker info >/dev/null 2>&1 && break
            sleep 2
        done
    fi
fi

if ! docker info >/dev/null 2>&1; then
    echo " [!] Docker n'est pas démarré. Lancez Docker Desktop puis relancez FQWorld."
    read -r -p " Appuyez sur Entrée pour fermer… "
    exit 1
fi

echo " Démarrage de FQWorld…"
docker compose up -d
echo " Attente de l'interface (quelques secondes)…"
ready=0
for _ in $(seq 1 60); do
    if curl -s -o /dev/null http://localhost:8501 2>/dev/null; then ready=1; break; fi
    sleep 2
done
if [ "$ready" = "1" ]; then
    echo " C'est prêt ! Ouverture de FQWorld…"
else
    echo " [!] L'interface met du temps à démarrer — ouvrez (ou actualisez)"
    echo "     cette page dans votre navigateur : http://localhost:8501"
fi
# Fenêtre applicative dédiée (comme un vrai logiciel) si Chrome/Chromium présent
URL=http://localhost:8501
if [ "$(uname)" = "Darwin" ] && [ -d "/Applications/Google Chrome.app" ]; then
    open -na "Google Chrome" --args --app=$URL --window-size=1320,920
elif command -v google-chrome >/dev/null 2>&1; then
    google-chrome --app=$URL --window-size=1320,920 >/dev/null 2>&1 &
elif command -v chromium >/dev/null 2>&1; then
    chromium --app=$URL --window-size=1320,920 >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then open $URL;
elif command -v xdg-open >/dev/null 2>&1; then xdg-open $URL; fi
