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


def _transcribe(audio_path: Path) -> str:
    client = _client()
    if client is None:
        return ""
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(model="whisper-1", file=f, language="fr")
    return result.text.strip()


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
        transcript = ""
        try:
            if audio_path is not None:
                transcript = _transcribe(audio_path)
        except Exception as exc:
            log.warning("Transcription Whisper impossible : %s", exc)
        try:
            verdict = _judge(transcript, chat_stats)
        except Exception as exc:
            log.warning("Validation LLM impossible : %s — clip conservé par défaut", exc)
            verdict = {"funny": True, "score": 0.5,
                       "title": "Moment fort du live 😂 #twitch #clip #fyp",
                       "reason": f"LLM indisponible ({exc})."}
        verdict["transcript"] = transcript
        return verdict

    result = await asyncio.to_thread(_work)
    if audio_path is not None:
        audio_path.unlink(missing_ok=True)
    return result
