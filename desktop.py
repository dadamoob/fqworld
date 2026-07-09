"""
FQWorld — application de bureau autonome (un seul exécutable).

Ce lanceur fait tout dans UN processus, sans Docker ni console :
1. démarre le Cerveau (surveillance Twitch) dans un thread,
2. démarre l'interface (serveur Streamlit) dans le processus principal,
3. ouvre FQWorld dans sa propre fenêtre d'application (Edge/Chrome --app),
4. affiche une icône près de l'horloge (Ouvrir / Quitter).

Packagé en FQWorld.exe par GitHub Actions (voir .github/workflows/build.yml).
Les données vivent dans un dossier « data » à côté de l'exécutable.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
# Ressources embarquées (app.py, agent/) : extraites dans _MEIPASS par PyInstaller
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
# Données utilisateur : à côté de l'exe (application portable) ou du dépôt
DATA_HOME = (Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent)

os.environ.setdefault("FQ_DATA_DIR", str(DATA_HOME / "data"))
sys.path.insert(0, str(BASE))

# En .exe fenêtré (sans console), stdout/stderr n'existent pas : sans cette
# redirection vers un fichier, le moindre print/log ferait planter l'app.
if FROZEN and (sys.stdout is None or sys.stderr is None):
    _log_stream = open(DATA_HOME / "fqworld.log", "a", buffering=1,
                       encoding="utf-8", errors="replace")
    sys.stdout = sys.stdout or _log_stream
    sys.stderr = sys.stderr or _log_stream

PORT = int(os.environ.get("FQ_PORT", "8501"))
URL = f"http://localhost:{PORT}"


def run_brain() -> None:
    """Le moteur de surveillance, dans un thread d'arrière-plan."""
    import asyncio

    from agent.brain import Brain
    try:
        asyncio.run(Brain().run_forever())
    except Exception:
        import logging
        logging.getLogger("desktop").exception("le cerveau s'est arrêté")


def _port_open() -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def open_app_window() -> None:
    """Ouvre FQWorld dans une fenêtre applicative dédiée (pas un onglet)."""
    candidates = []
    if sys.platform == "win32":
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        local = os.environ.get("LocalAppData", "")
        candidates = [
            Path(pf86) / "Microsoft/Edge/Application/msedge.exe",
            Path(pf) / "Microsoft/Edge/Application/msedge.exe",
            Path(pf) / "Google/Chrome/Application/chrome.exe",
            Path(local) / "Google/Chrome/Application/chrome.exe" if local else None,
        ]
    elif sys.platform == "darwin":
        candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    else:
        import shutil
        for name in ("google-chrome", "chromium", "chromium-browser"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

    for browser in candidates:
        if browser and browser.is_file():
            subprocess.Popen([str(browser), f"--app={URL}", "--window-size=1320,920"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    webbrowser.open(URL)  # à défaut : navigateur normal


def wait_then_open() -> None:
    for _ in range(120):
        if _port_open():
            break
        time.sleep(1)
    if os.environ.get("FQ_NO_BROWSER") != "1":
        open_app_window()


def run_tray() -> None:
    """Icône près de l'horloge : Ouvrir FQWorld / Quitter. Optionnelle."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        return  # pas de tray disponible : l'app reste pilotée par la fenêtre

    # petite icône générée : carré dégradé violet avec un triangle "play"
    img = Image.new("RGB", (64, 64), "#9146FF")
    draw = ImageDraw.Draw(img)
    for y in range(64):  # dégradé Twitch -> TikTok
        ratio = y / 63
        draw.line([(0, y), (63, y)],
                  fill=(int(0x91 + (0xFF - 0x91) * ratio),
                        int(0x46 + (0x2D - 0x46) * ratio),
                        int(0xFF + (0x74 - 0xFF) * ratio)))
    draw.polygon([(24, 18), (24, 46), (48, 32)], fill="white")

    menu = pystray.Menu(
        pystray.MenuItem("Ouvrir FQWorld", lambda: open_app_window(), default=True),
        pystray.MenuItem("Quitter", lambda icon: (icon.stop(), os._exit(0))),
    )
    pystray.Icon("FQWorld", img, "FQWorld — agent Twitch → TikTok", menu).run()


def main() -> None:
    threading.Thread(target=run_brain, daemon=True, name="brain").start()
    threading.Thread(target=wait_then_open, daemon=True, name="opener").start()
    threading.Thread(target=run_tray, daemon=True, name="tray").start()

    # Interface : serveur Streamlit dans le processus principal
    from streamlit.web import bootstrap
    flag_options = {
        "server.address": "127.0.0.1",
        "server.port": PORT,
        "server.headless": True,
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
    }
    bootstrap.load_config_options(flag_options=flag_options)
    bootstrap.run(str(BASE / "app.py"), False, [], flag_options)


if __name__ == "__main__":
    main()
