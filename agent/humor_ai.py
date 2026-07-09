"""
Validation IA d'un moment détecté :
1. Whisper transcrit l'audio des ~30 dernières secondes.
2. Un LLM rapide (gpt-4o-mini) lit la transcription + les stats du chat
   et rend un verdict JSON : drôle ou non, score, titre TikTok suggéré.

Le pic de chat est le déclencheur "pas cher" ; l'IA est le filtre qualité.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from openai import OpenAI

from . import storage

log = logging.getLogger("humor_ai")

JUDGE_PROMPT = """Tu es un expert en contenu viral TikTok pour la communauté gaming/stream FR.
On te donne la transcription des 30 dernières secondes d'un live Twitch, pendant lesquelles
le chat a explosé de rires (statistiques fournies).

Réponds UNIQUEMENT en JSON avec ces clés :
- "funny": true/false — la séquence est-elle réellement drôle/interactive/clipable ?
- "score": nombre entre 0 et 1 — potentiel viral estimé
- "title": un titre TikTok court et accrocheur en français (avec 2-3 hashtags)
- "reason": une phrase expliquant ton verdict

Sois exigeant : une transcription vide, incompréhensible ou banale => funny=false."""


def _client() -> OpenAI | None:
    api_key = storage.get_config("openai_api_key")
    if not api_key:
        log.warning("Clé OpenAI absente : ajoutez-la dans l'onglet Configuration de l'UI.")
        return None
    return OpenAI(api_key=api_key)


def _transcribe(audio_path: Path) -> tuple[str, list[dict]]:
    """Retourne (texte, segments horodatés) pour les sous-titres incrustés."""
    client = _client()
    if client is None:
        return "", []
    language = storage.get_config("language") or "fr"
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-1", file=f, language=language,
            response_format="verbose_json",
        )
    segments = []
    for seg in (getattr(result, "segments", None) or []):
        get = seg.get if isinstance(seg, dict) else lambda k, s=seg: getattr(s, k, None)
        text = (get("text") or "").strip()
        if text:
            segments.append({"start": float(get("start") or 0),
                             "end": float(get("end") or 0), "text": text})
    return (result.text or "").strip(), segments


def _judge(transcript: str, chat_stats: dict) -> dict:
    client = _client()
    if client is None:
        # Pas de clé => on garde le clip par défaut (le pic de chat suffit),
        # l'utilisateur tranchera dans la bibliothèque.
        return {"funny": True, "score": 0.5,
                "title": "Moment fort du live 😂 #twitch #clip #fyp",
                "reason": "Validation IA désactivée (pas de clé OpenAI)."}
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content":
                f"Statistiques du chat : {json.dumps(chat_stats)}\n\n"
                f"Transcription :\n{transcript or '(aucune parole détectée)'}"},
        ],
        temperature=0.3,
    )
    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, IndexError):
        return {"funny": False, "score": 0, "title": "", "reason": "Réponse LLM illisible."}


async def validate_clip(audio_path: Path | None, chat_stats: dict) -> dict:
    """Retourne {"funny", "score", "title", "reason", "transcript"} sans bloquer l'event loop."""
    def _work() -> dict:
        transcript, segments = "", []
        try:
            if audio_path is not None:
                transcript, segments = _transcribe(audio_path)
        except Exception as exc:
            log.warning("Transcription Whisper impossible : %s", exc)
        try:
            verdict = _judge(transcript, chat_stats)
        except Exception as exc:
            log.warning("Validation LLM impossible : %s — clip conservé par défaut", exc)
            verdict = {"funny": True, "score": 0.5,
                       "title": "Moment fort du live 😂",
                       "reason": f"LLM indisponible ({exc})."}
        # hashtags par défaut ajoutés au titre s'il n'en contient pas
        hashtags = (storage.get_config("default_hashtags") or "").strip()
        title = (verdict.get("title") or "").strip()
        if title and hashtags and "#" not in title:
            verdict["title"] = f"{title} {hashtags}"
        verdict["transcript"] = transcript
        verdict["segments"] = segments
        return verdict

    result = await asyncio.to_thread(_work)
    if audio_path is not None:
        audio_path.unlink(missing_ok=True)
    return result
