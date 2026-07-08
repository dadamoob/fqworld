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
echo " [2/3] Création du raccourci sur le Bureau…"
HERE="$(pwd)"
chmod +x FQWorld.sh stop.sh install.sh 2>/dev/null || true
DESKTOP="$HOME/Desktop"
[ -d "$HOME/Bureau" ] && DESKTOP="$HOME/Bureau"   # Linux en français
if [ -d "$DESKTOP" ]; then
    if [ "$(uname)" = "Darwin" ]; then
        # macOS : un .command se lance en double-clic
        printf '#!/usr/bin/env bash\ncd "%s"\nexec bash FQWorld.sh\n' "$HERE" > "$DESKTOP/FQWorld.command"
        chmod +x "$DESKTOP/FQWorld.command"
        echo "      Raccourci « FQWorld.command » créé sur le Bureau !"
    else
        # Linux : fichier .desktop
        cat > "$DESKTOP/FQWorld.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=FQWorld
Comment=Agent Twitch vers TikTok
Exec=bash -c 'cd "$HERE" && bash FQWorld.sh'
Terminal=true
Icon=video-display
EOF
        chmod +x "$DESKTOP/FQWorld.desktop"
        echo "      Raccourci « FQWorld » créé sur le Bureau !"
        echo "      (au premier double-clic, choisissez « Autoriser le lancement » si demandé)"
    fi
else
    echo "      [i] Pas de dossier Bureau trouvé — utilisez : bash FQWorld.sh"
fi

echo ""
echo " [3/3] C'est prêt !"
echo ""
echo "  Au quotidien : double-cliquez sur le raccourci FQWorld du Bureau"
echo "                 (il démarre même Docker si besoin)"
echo "  Interface    : http://localhost:8501"
echo "  Arrêter      : bash stop.sh"
echo ""
if command -v open >/dev/null 2>&1; then open http://localhost:8501;
elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:8501; fi
