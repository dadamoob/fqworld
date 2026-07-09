"""
Capture vidéo et montage automatique au format TikTok (9:16).

Stratégie : tant qu'un streamer est en live, son flux est enregistré en
continu dans des segments de 10 s (buffer circulaire sur disque, on ne
garde que les ~3 dernières minutes). Quand le chat explose de rire, on
recolle les N derniers segments et on recadre en 1080x1920 avec FFmpeg.
=> le clip contient les secondes qui PRÉCÈDENT le pic (le moment drôle).

Le flux est lu via la bibliothèque streamlink (agent/media.py) : aucune
commande externe autre que FFmpeg, condition pour l'app .exe autonome.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from . import media, storage

log = logging.getLogger("clipper")

SEGMENT_SECONDS = 10
KEEP_SEGMENTS = 20  # 20 x 10 s = ~3 min de mémoire tampon


class RollingRecorder:
    """Enregistre le live d'un streamer en segments, avec buffer circulaire."""

    def __init__(self, channel: str):
        self.channel = channel
        self.dir = storage.DATA_DIR / "buffers" / channel
        self._proc: subprocess.Popen | None = None
        self._stop_pump = threading.Event()

    def start(self) -> None:
        if self.running:
            return
        # repart d'un buffer vierge : numérotation séquentielle sans collision
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            stream_fd = media.open_stream(f"https://twitch.tv/{self.channel}")
        except Exception as exc:
            log.warning("[%s] flux injoignable : %s", self.channel, exc)
            return
        if stream_fd is None:
            log.warning("[%s] aucun flux disponible (hors ligne ?)", self.channel)
            return
        # ffmpeg découpe le flux en segments .ts (buffer circulaire)
        self._proc = subprocess.Popen(
            [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0",
             "-c", "copy",
             "-f", "segment",
             "-segment_time", str(SEGMENT_SECONDS),
             "-reset_timestamps", "1",
             str(self.dir / "seg_%06d.ts")],
            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self._stop_pump = threading.Event()
        threading.Thread(target=media.pump,
                         args=(stream_fd, self._proc.stdin, self._stop_pump),
                         daemon=True).start()
        log.info("[%s] enregistrement tampon démarré", self.channel)

    def stop(self) -> None:
        self._stop_pump.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
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
            [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c", "copy", str(raw)],
            capture_output=True,
        )
        return raw if result.returncode == 0 else None


def crop_to_tiktok(source: Path, channel: str) -> Path | None:
    """Recadre la vidéo en 9:16 (1080x1920) centré — format TikTok."""
    storage.CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    out = storage.CLIPS_DIR / f"{channel}_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    # crop central 9:16 puis mise à l'échelle 1080x1920
    vf = "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,setsar=1"
    result = subprocess.run(
        [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
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


_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTok,Arial,68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,70,70,430,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return (f"{int(seconds // 3600)}:{int(seconds % 3600 // 60):02d}:"
            f"{seconds % 60:05.2f}")


def burn_subtitles(video: Path, segments: list[dict]) -> Path:
    """Incruste des sous-titres style TikTok (gros, blancs, contour noir).

    `segments` : [{"start": s, "end": s, "text": "..."}] issus de Whisper.
    Retourne le nouveau fichier (ou l'original si rien à incruster / échec).
    """
    lines = []
    for seg in segments:
        text = str(seg.get("text", "")).strip().replace("{", "").replace("}", "")
        if not text:
            continue
        lines.append(f"Dialogue: 0,{_ass_time(float(seg['start']))},"
                     f"{_ass_time(float(seg['end']))},TikTok,,0,0,0,,{text}")
    if not lines:
        return video

    ass = video.with_suffix(".ass")
    ass.write_text(_ASS_HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    out = video.with_name(video.stem + "_sub.mp4")
    result = subprocess.run(
        [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video), "-vf", f"ass={ass}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-c:a", "copy", "-movflags", "+faststart", str(out)],
        capture_output=True,
    )
    ass.unlink(missing_ok=True)
    if result.returncode != 0 or not out.exists():
        log.warning("incrustation des sous-titres échouée : %s",
                    result.stderr.decode()[-300:])
        out.unlink(missing_ok=True)
        return video
    video.unlink(missing_ok=True)
    return out


def extract_audio(video: Path) -> Path | None:
    """Extrait l'audio en mp3 léger pour la transcription Whisper."""
    audio = video.with_suffix(".mp3")
    result = subprocess.run(
        [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
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
