"""
LE CERVEAU — orchestrateur en arrière-plan.  Lancement : python -m agent.brain

Boucle toutes les 60 s :
1. Lit la liste des streamers ajoutés dans l'UI (base SQLite partagée).
2. Vérifie qui est en live via l'API Twitch Helix -> met à jour le Dashboard.
3. Pour chaque streamer en live : démarre l'écoute du chat (ChatMonitor)
   et l'enregistrement tampon du flux (RollingRecorder).
4. Sur pic de rires : extrait les 30 dernières secondes, recadre en 9:16,
   fait valider par l'IA (Whisper + LLM), range le clip dans la bibliothèque,
   et le publie sur TikTok si l'auto-post est activé dans l'UI.
5. Traite aussi les analyses de REDIFFUSIONS (VOD) demandées dans l'UI,
   une à la fois (agent/vod_hunter.py).
"""

from __future__ import annotations

import asyncio
import logging

from . import storage, twitch_api
from .chat_monitor import ChatMonitor
from .clipper import RollingRecorder, capture_clip, extract_audio
from .humor_ai import validate_clip
from .tiktok_publisher import publish_to_tiktok
from .vod_hunter import run_vod_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("brain")

POLL_INTERVAL = 60  # secondes entre deux vérifications live/config


class Brain:
    def __init__(self):
        self.monitors: dict[str, ChatMonitor] = {}
        self.monitor_tasks: dict[str, asyncio.Task] = {}
        self.recorders: dict[str, RollingRecorder] = {}
        self.vod_task: asyncio.Task | None = None

    # ------------------------------------------------------ cycle principal

    async def run_forever(self) -> None:
        log.info("🧠 Cerveau démarré — en attente de streamers ajoutés dans l'UI…")
        while True:
            try:
                await self._tick()
            except Exception:
                log.exception("Erreur dans le cycle principal (on continue)")
            await asyncio.sleep(POLL_INTERVAL)

    async def _tick(self) -> None:
        streamers = [s["username"] for s in storage.list_streamers()]
        try:
            live = await asyncio.to_thread(twitch_api.get_live_streams, streamers)
        except twitch_api.TwitchConfigError as exc:
            if streamers:
                log.warning(str(exc))
            live = {}

        for username in streamers:
            is_live = username in live
            storage.set_live_status(username, is_live, live.get(username, ""))
            if is_live:
                self._start_watching(username)
            else:
                self._stop_watching(username)

        # streamers retirés de l'UI => on coupe tout
        for username in list(self.monitors):
            if username not in streamers:
                self._stop_watching(username)

        # purge des buffers vidéo (mémoire tampon circulaire)
        for recorder in self.recorders.values():
            if recorder.running:
                recorder.prune()

        # analyses de rediffusions demandées dans l'UI (une à la fois)
        if self.vod_task is None or self.vod_task.done():
            job = storage.claim_next_vod_job()
            if job is not None:
                self.vod_task = asyncio.create_task(run_vod_job(job))

    def _start_watching(self, username: str) -> None:
        if username not in self.recorders:
            self.recorders[username] = RollingRecorder(username)
        if not self.recorders[username].running:
            self.recorders[username].start()

        if username not in self.monitors:
            threshold = float(storage.get_config("laugh_threshold") or 4)
            monitor = ChatMonitor(username, threshold, self._on_spike)
            self.monitors[username] = monitor
            self.monitor_tasks[username] = asyncio.create_task(monitor.run())
            log.info("[%s] 👀 surveillance active (chat + flux vidéo)", username)

    def _stop_watching(self, username: str) -> None:
        if username in self.monitors:
            self.monitors.pop(username).stop()
            self.monitor_tasks.pop(username).cancel()
            log.info("[%s] surveillance arrêtée (hors ligne ou retiré)", username)
        if username in self.recorders:
            self.recorders.pop(username).stop()

    # -------------------------------------------------- pipeline d'un clip

    async def _on_spike(self, channel: str, chat_stats: dict) -> None:
        """Appelé par ChatMonitor quand le chat explose de rire."""
        recorder = self.recorders.get(channel)
        if recorder is None or not recorder.running:
            return

        duration = int(float(storage.get_config("clip_duration") or 30))
        log.info("[%s] ✂️  extraction des %d dernières secondes…", channel, duration)
        video = await capture_clip(recorder, duration)
        if video is None:
            log.warning("[%s] extraction impossible (buffer trop court ?)", channel)
            return

        # Validation IA : Whisper transcrit, le LLM juge
        audio = await asyncio.to_thread(extract_audio, video)
        verdict = await validate_clip(audio, chat_stats)

        if not verdict.get("funny"):
            storage.add_clip(
                streamer=channel, path=str(video),
                title=verdict.get("title") or "Séquence rejetée",
                status=storage.CLIP_REJECTED,
                transcript=verdict.get("transcript", ""),
                humor_score=float(verdict.get("score") or 0),
                error=verdict.get("reason", ""),
            )
            log.info("[%s] 🟡 clip rejeté par l'IA : %s", channel, verdict.get("reason"))
            return

        clip_id = storage.add_clip(
            streamer=channel, path=str(video),
            title=verdict.get("title") or f"Moment fort de {channel} 😂",
            status=storage.CLIP_READY,
            transcript=verdict.get("transcript", ""),
            humor_score=float(verdict.get("score") or 0),
        )
        log.info("[%s] 🟢 clip validé par l'IA (score %.0f%%) -> bibliothèque",
                 channel, float(verdict.get("score") or 0) * 100)

        if storage.get_config("auto_post") == "true":
            ok, message = await asyncio.to_thread(
                publish_to_tiktok, str(video), verdict.get("title", ""))
            if ok:
                storage.update_clip_status(clip_id, storage.CLIP_POSTED)
                log.info("[%s] 🚀 clip publié automatiquement sur TikTok", channel)
            else:
                storage.update_clip_status(clip_id, storage.CLIP_FAILED, error=message)
                log.warning("[%s] 🔴 publication TikTok échouée : %s", channel, message)


if __name__ == "__main__":
    try:
        asyncio.run(Brain().run_forever())
    except KeyboardInterrupt:
        log.info("Cerveau arrêté.")
