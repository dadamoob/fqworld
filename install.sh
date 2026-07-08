#!/usr/bin/env bash
# ============================================================
#  FQWorld — Installation en une commande (Mac / Linux)
#  Usage :  bash install.sh
# ============================================================
set -e
cd "$(dirname "$0")"

echo ""
echo " ============================================"
echo "  FQWorld — Agent Twitch → TikTok"
echo " ============================================"
echo ""

if ! command -v docker >/dev/null 2>&1; then
    echo " [!] Docker n'est pas installé."
    echo "     Téléchargez Docker Desktop ici puis relancez ce script :"
    echo "     https://www.docker.com/products/docker-desktop/"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo " [!] Docker est installé mais pas démarré."
    echo "     Lancez Docker Desktop (icône baleine) puis relancez ce script."
    exit 1
fi

echo " [1/2] Construction et démarrage de l'agent…"
echo "       (le premier lancement prend 2 à 5 minutes)"
echo ""
docker compose up --build -d

echo ""
echo " [2/2] C'est prêt !"
echo ""
echo "  Interface : http://localhost:8501"
echo "  Arrêter   : bash stop.sh"
echo ""
if command -v open >/dev/null 2>&1; then open http://localhost:8501;
elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8501; fi
