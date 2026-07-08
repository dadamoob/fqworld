"""
Analyse des rediffusions (VOD) Twitch pour en extraire des clips.

Contrairement au live, une VOD n'a pas de chat en temps réel exploitable
simplement. On utilise donc l'AUDIO comme détecteur de moments forts :
1. On streame la piste audio de la VOD (streamlink, sans télécharger la vidéo)
   et on mesure le volume seconde par seconde avec FFmpeg.
2. Les pics de volume (cris, éclats de rire du streamer) = candidats.
3. Pour chaque candidat, on télécharge UNIQUEMENT les ~30 secondes concernées,
   on recadre en 9:16, puis Whisper + LLM valident si c'est vraiment drôle.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import uuid
from pathlib import Path

from . import storage
from .clipper import crop_to_tiktok, extract_audio
from .humor_ai import validate_clip

log = logging.getLogger("vod_hunter")

PEAK_MARGIN_DB = 6      # un pic = volume > médiane + 6 dB
MIN_GAP_SECONDS = 180   # écart minimum entre deux clips d'une même VOD
LEAD_SECONDS = 22       # le clip démarre ~22 s avant le pic (le contexte)


def _hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


# ------------------------------------------------------------ scan audio

def scan_audio_peaks(vod_url: str, count: int, vod_duration: float,
                     progress_cb=None) -> list[tuple[float, float]]:
    """Streame l'audio de la VOD et retourne les `count` plus gros pics [(t, dB)]."""
    streamlink = subprocess.Popen(
        ["streamlink", "--stdout", vod_url, "audio_only,worst"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    # astats avec reset toutes les ~1 s => volume RMS seconde par seconde
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-af", ("asetnsamples=48000,astats=metadata=1:reset=1,"
                 "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-"),
         "-f", "null", "-"],
        stdin=streamlink.stdout, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True,
    )
    streamlink.stdout.close()

    levels: list[tuple[float, float]] = []
    current_t: float | None = None
    for line in ffmpeg.stdout:
        line = line.strip()
        if line.startswith("frame:"):
            match = re.search(r"pts_time:([\d.]+)", line)
            current_t = float(match.group(1)) if match else None
        elif "RMS_level=" in line and current_t is not None:
            value = line.split("=", 1)[1]
            if value not in ("-inf", "nan", "inf"):
                levels.append((current_t, float(value)))
            if progress_cb and len(levels) % 120 == 0 and vod_duration > 0:
                progress_cb(min(1.0, current_t / vod_duration))
    ffmpeg.wait()
    streamlink.wait()

    if not levels:
        return []

    # médiane du volume = "ambiance normale" du stream
    sorted_vals = sorted(v for _, v in levels)
    median = sorted_vals[len(sorted_vals) // 2]

    candidates = sorted(
        [(t, v) for t, v in levels if v > median + PEAK_MARGIN_DB],
        key=lambda item: -item[1],
    )
    chosen: list[tuple[float, float]] = []
    for t, v in candidates:
        if all(abs(t - c[0]) > MIN_GAP_SECONDS for c in chosen):
            chosen.append((t, v))
        if len(chosen) >= count:
            break
    return sorted(chosen)  # ordre chronologique


# ------------------------------------------------- extraction d'un segment

def extract_vod_segment(vod_url: str, start: float, duration: int) -> Path | None:
    """Télécharge uniquement `duration` secondes de la VOD à partir de `start`."""
    out_dir = storage.DATA_DIR / "buffers"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / f"vod_{uuid.uuid4().hex[:8]}.ts"

    streamlink = subprocess.Popen(
        ["streamlink", "--stdout",
         "--hls-start-offset", _hms(start),
         "--hls-duration", _hms(duration + 8),
         vod_url, "720p,best"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", "pipe:0", "-t", str(duration), "-c", "copy", str(raw)],
        stdin=streamlink.stdout, capture_output=True,
    )
    streamlink.stdout.close()
    streamlink.wait()
    if result.returncode != 0 or not raw.exists():
        raw.unlink(missing_ok=True)
        return None
    return raw


# --------------------------------------------------------- job complet

async def run_vod_job(job: dict) -> None:
    """Pipeline complet d'une analyse de rediffusion (appelé par le Cerveau)."""
    job_id = job["id"]
    log.info("[%s] 📼 analyse de la rediffusion « %s »", job["streamer"], job["vod_title"])
    try:
        peaks = await asyncio.to_thread(
            scan_audio_peaks, job["vod_url"], int(job["clips_wanted"]),
            float(job["vod_duration"]),
            lambda p: storage.update_vod_job(job_id, progress=round(0.7 * p, 3)),
        )
        if not peaks:
            storage.update_vod_job(job_id, status=storage.JOB_FAILED,
                                   error="Aucun moment fort détecté dans l'audio.")
            return

        storage.update_vod_job(job_id, progress=0.7)
        clip_duration = int(float(storage.get_config("clip_duration") or 30))
        found = 0
        for index, (t, peak_db) in enumerate(peaks, start=1):
            log.info("[%s] pic audio à %s (%.1f dB) -> extraction",
                     job["streamer"], _hms(t), peak_db)
            raw = await asyncio.to_thread(
                extract_vod_segment, job["vod_url"],
                max(0.0, t - LEAD_SECONDS), clip_duration)
            if raw is None:
                continue
            clip = await asyncio.to_thread(crop_to_tiktok, raw, job["streamer"])
            if clip is None:
                continue
            audio = await asyncio.to_thread(extract_audio, clip)
            verdict = await validate_clip(
                audio, {"source": "rediffusion", "horodatage": _hms(t),
                        "pic_audio_db": round(peak_db, 1)})

            is_funny = bool(verdict.get("funny"))
            storage.add_clip(
                streamer=job["streamer"], path=str(clip),
                title=verdict.get("title") or f"Moment fort de {job['streamer']} 😂",
                status=storage.CLIP_READY if is_funny else storage.CLIP_REJECTED,
                transcript=verdict.get("transcript", ""),
                humor_score=float(verdict.get("score") or 0),
                error="" if is_funny else verdict.get("reason", ""),
            )
            found += int(is_funny)
            storage.update_vod_job(
                job_id, clips_found=found,
                progress=round(0.7 + 0.3 * index / len(peaks), 3))

        storage.update_vod_job(job_id, status=storage.JOB_DONE, progress=1.0,
                               clips_found=found)
        log.info("[%s] 📼 analyse terminée : %d clip(s) validé(s)", job["streamer"], found)
    except Exception as exc:
        log.exception("[%s] analyse de rediffusion échouée", job["streamer"])
        storage.update_vod_job(job_id, status=storage.JOB_FAILED, error=str(exc))
