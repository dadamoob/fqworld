"""
Capture vidéo et montage automatique au format TikTok (9:16).

Stratégie : tant qu'un streamer est en live, `streamlink` enregistre son flux
en continu dans des segments de 10 s (buffer circulaire sur disque, on ne
garde que les ~3 dernières minutes). Quand le chat explose de rire, on
recolle les N derniers segments et on recadre en 1080x1920 avec FFmpeg.
=> le clip contient les secondes qui PRÉCÈDENT le pic (le moment drôle).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from . import storage

log = logging.getLogger("clipper")

SEGMENT_SECONDS = 10
KEEP_SEGMENTS = 20  # 20 x 10 s = ~3 min de mémoire tampon


class RollingRecorder:
    """Enregistre le live d'un streamer en segments, avec buffer circulaire."""

    def __init__(self, channel: str):
        self.channel = channel
        self.dir = storage.DATA_DIR / "buffers" / channel
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        # streamlink tire le flux Twitch -> ffmpeg le découpe en segments .ts
        streamlink = subprocess.Popen(
            ["streamlink", "--twitch-disable-ads", "--stdout",
             f"https://twitch.tv/{self.channel}", "720p,best"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self._proc = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0",
             "-c", "copy",
             "-f", "segment",
             "-segment_time", str(SEGMENT_SECONDS),
             "-reset_timestamps", "1",
             "-strftime", "1",
             str(self.dir / "seg_%Y%m%d_%H%M%S.ts")],
            stdin=streamlink.stdout, stderr=subprocess.DEVNULL,
        )
        streamlink.stdout.close()
        self._streamlink = streamlink
        log.info("[%s] enregistrement tampon démarré", self.channel)

    def stop(self) -> None:
        for proc in (getattr(self, "_streamlink", None), self._proc):
            if proc and proc.poll() is None:
                proc.terminate()
        self._proc = None
        shutil.rmtree(self.dir, ignore_errors=True)
        log.info("[%s] enregistrement tampon arrêté", self.channel)

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def prune(self) -> None:
        """Ne garde que les KEEP_SEGMENTS segments les plus récents."""
        segments = sorted(self.dir.glob("seg_*.ts"))
        for old in segments[:-KEEP_SEGMENTS]:
            old.unlink(missing_ok=True)

    def extract_last(self, seconds: int) -> Path | None:
        """Recolle les derniers `seconds` du buffer dans un .ts temporaire."""
        # Le dernier segment est probablement encore en cours d'écriture : on l'ignore.
        segments = sorted(self.dir.glob("seg_*.ts"))[:-1]
        if not segments:
            return None
        needed = max(1, round(seconds / SEGMENT_SECONDS))
        chosen = segments[-needed:]

        concat_list = self.dir / "concat.txt"
        concat_list.write_text("".join(f"file '{p.name}'\n" for p in chosen))
        raw = self.dir / f"raw_{uuid.uuid4().hex[:8]}.ts"
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c", "copy", str(raw)],
            capture_output=True,
        )
        return raw if result.returncode == 0 else None


def crop_to_tiktok(source: Path, channel: str) -> Path | None:
    """Recadre la vidéo en 9:16 (1080x1920) centré — format TikTok."""
    out = storage.CLIPS_DIR / f"{channel}_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    # crop central 9:16 puis mise à l'échelle 1080x1920
    vf = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,setsar=1"
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(source),
         "-vf", vf,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart",
         str(out)],
        capture_output=True,
    )
    source.unlink(missing_ok=True)
    if result.returncode != 0:
        log.error("[%s] échec du recadrage FFmpeg : %s", channel, result.stderr.decode()[-400:])
        return None
    return out


def extract_audio(video: Path) -> Path | None:
    """Extrait l'audio en mp3 léger pour la transcription Whisper."""
    audio = video.with_suffix(".mp3")
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(audio)],
        capture_output=True,
    )
    return audio if result.returncode == 0 else None


async def capture_clip(recorder: RollingRecorder, seconds: int) -> Path | None:
    """Pipeline complet en thread pour ne pas bloquer l'event loop asyncio."""
    def _work() -> Path | None:
        raw = recorder.extract_last(seconds)
        if raw is None:
            return None
        return crop_to_tiktok(raw, recorder.channel)
    return await asyncio.to_thread(_work)
