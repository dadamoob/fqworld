"""
Surveillance du chat Twitch + détection des pics de rires.

La lecture du chat Twitch se fait en IRC anonyme (pseudo justinfanXXXX) :
aucune clé API n'est nécessaire pour LIRE un chat public.

Principe de détection :
- on compte les messages "rires" (LUL, MDR, KEKW…) par fenêtre glissante de 10 s
- on maintient une moyenne de fond (baseline) de cette activité
- si l'activité instantanée dépasse baseline × seuil (configurable dans l'UI),
  on déclenche un événement "moment drôle potentiel".
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import deque
from typing import Awaitable, Callable

log = logging.getLogger("chat_monitor")

TWITCH_IRC_HOST = "irc.chat.twitch.tv"
TWITCH_IRC_PORT = 6667

# Emotes / expressions qui signalent le rire dans un chat Twitch (FR + EN)
LAUGH_PATTERN = re.compile(
    r"\b(lul+|lol+|mdr+|ptdr+|kekw|omegalul|lmao+|xd+|haha+|jaja+|wtf|"
    r"pog+|pogchamp|icant|sourire)\b|(?:😂|🤣|💀){1,}",
    re.IGNORECASE,
)

WINDOW_SECONDS = 10       # taille de la fenêtre d'analyse
BASELINE_ALPHA = 0.05     # lissage exponentiel de la baseline
MIN_LAUGHS_ABSOLUTE = 8   # plancher absolu pour éviter les faux positifs sur petits chats
COOLDOWN_SECONDS = 120    # délai minimum entre deux clips d'un même streamer


class ChatMonitor:
    """Écoute le chat d'UN streamer et appelle `on_spike` sur pic de rires."""

    def __init__(self, channel: str, laugh_threshold: float,
                 on_spike: Callable[[str, dict], Awaitable[None]]):
        self.channel = channel.lower()
        self.laugh_threshold = laugh_threshold
        self.on_spike = on_spike
        self._laugh_times: deque[float] = deque()
        self._baseline = 1.0          # rires/fenêtre "normaux" (jamais 0 pour éviter division)
        self._last_spike = 0.0
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        """Boucle principale : connexion IRC + reconnexion automatique."""
        while not self._stop.is_set():
            try:
                await self._listen()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("[%s] connexion chat perdue (%s), reconnexion dans 5 s", self.channel, exc)
                await asyncio.sleep(5)

    async def _listen(self) -> None:
        reader, writer = await asyncio.open_connection(TWITCH_IRC_HOST, TWITCH_IRC_PORT)
        nick = f"justinfan{random.randint(10000, 99999)}"  # connexion anonyme lecture seule
        writer.write(f"NICK {nick}\r\nJOIN #{self.channel}\r\n".encode())
        await writer.drain()
        log.info("[%s] connecté au chat Twitch (anonyme)", self.channel)

        try:
            while not self._stop.is_set():
                raw = await asyncio.wait_for(reader.readline(), timeout=300)
                if not raw:
                    raise ConnectionError("flux IRC fermé")
                line = raw.decode(errors="ignore").strip()

                if line.startswith("PING"):
                    writer.write(line.replace("PING", "PONG").encode() + b"\r\n")
                    await writer.drain()
                    continue

                if "PRIVMSG" in line:
                    message = line.split("PRIVMSG", 1)[1].split(":", 1)[-1]
                    self._on_message(message)
        finally:
            writer.close()

    # ------------------------------------------------------------- détection

    def _on_message(self, message: str) -> None:
        now = time.time()
        if LAUGH_PATTERN.search(message):
            self._laugh_times.append(now)

        # purge de la fenêtre glissante
        while self._laugh_times and self._laugh_times[0] < now - WINDOW_SECONDS:
            self._laugh_times.popleft()

        current = len(self._laugh_times)

        # détection de pic AVANT mise à jour de la baseline
        is_spike = (
            current >= MIN_LAUGHS_ABSOLUTE
            and current >= self._baseline * self.laugh_threshold
            and now - self._last_spike > COOLDOWN_SECONDS
        )

        # la baseline apprend l'activité "normale" du chat en continu
        self._baseline = (1 - BASELINE_ALPHA) * self._baseline + BASELINE_ALPHA * max(current, 1)

        if is_spike:
            self._last_spike = now
            stats = {"laughs_in_window": current, "baseline": round(self._baseline, 1),
                     "ratio": round(current / self._baseline, 1)}
            log.info("[%s] 🎉 PIC DE RIRES détecté ! %s", self.channel, stats)
            asyncio.get_running_loop().create_task(self.on_spike(self.channel, stats))
