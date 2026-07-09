"""
Accès aux flux Twitch et à FFmpeg, compatible application autonome (.exe).

Tout passe par la bibliothèque Python de streamlink (aucune commande externe
`streamlink`) et par un chemin FFmpeg résolu dynamiquement : indispensable
pour que FQWorld fonctionne aussi bien en Docker qu'en .exe PyInstaller,
où seuls l'exécutable et ses ressources embarquées existent.
"""

from __future__ import annotations

import logging
import shutil
import sys
import threading
from pathlib import Path

from streamlink.session import Streamlink

log = logging.getLogger("media")


def ffmpeg_bin() -> str:
    """FFmpeg embarqué (app gelée) sinon celui du système."""
    if getattr(sys, "frozen", False):
        candidates = [
            Path(getattr(sys, "_MEIPASS", "")) / "ffmpeg.exe",
            Path(getattr(sys, "_MEIPASS", "")) / "ffmpeg",
            Path(sys.executable).parent / "ffmpeg.exe",
            Path(sys.executable).parent / "ffmpeg",
        ]
        for cand in candidates:
            if cand and cand.is_file():
                return str(cand)
    return shutil.which("ffmpeg") or "ffmpeg"


def open_stream(url: str, qualities: tuple[str, ...] = ("720p", "best"),
                start_offset: float = 0.0, duration: float = 0.0):
    """Ouvre un flux Twitch (live ou VOD) et retourne un objet lisible (bytes).

    Retourne None si aucun flux n'est disponible (hors ligne, VOD supprimée…).
    """
    session = Streamlink()
    for key, value in (("stream-timeout", 60.0),
                       ("hls-start-offset", float(start_offset)),
                       ("hls-duration", float(duration))):
        if value:
            try:
                session.set_option(key, value)
            except Exception as exc:
                log.debug("option streamlink %s ignorée : %s", key, exc)
    try:  # saute les coupures pub de Twitch quand le plugin le permet
        session.set_option("twitch-disable-ads", True)
    except Exception:
        pass

    streams = session.streams(url)
    if not streams:
        return None
    for quality in qualities:
        if quality in streams:
            return streams[quality].open()
    return next(iter(streams.values())).open()


def pump(stream_fd, sink, stop_event: threading.Event | None = None,
         chunk: int = 65536) -> None:
    """Copie un flux vers l'entrée d'un processus FFmpeg (cible de thread)."""
    try:
        while stop_event is None or not stop_event.is_set():
            data = stream_fd.read(chunk)
            if not data:
                break
            sink.write(data)
    except (BrokenPipeError, OSError, ValueError):
        pass  # ffmpeg fermé ou flux coupé : fin normale
    finally:
        for closable in (sink, stream_fd):
            try:
                closable.close()
            except Exception:
                pass
