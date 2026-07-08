#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "Arrêt de FQWorld…"
docker compose down
echo "FQWorld est arrêté. Vos clips et votre configuration sont conservés dans le dossier data/"
