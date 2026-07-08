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
echo " Ouverture de l'interface…"
sleep 3
if command -v open >/dev/null 2>&1; then open http://localhost:8501;
elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8501; fi
