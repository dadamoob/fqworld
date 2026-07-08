"""
Publication sur TikTok via la Content Posting API officielle (Direct Post).
Docs : https://developers.tiktok.com/doc/content-posting-api-get-started

Prérequis (une seule fois, hors code) :
1. Créer une app sur https://developers.tiktok.com et demander l'accès
   à la "Content Posting API" (validation par TikTok requise).
2. Obtenir un access token OAuth avec le scope `video.publish`.
3. Coller ce token dans l'onglet Configuration de l'UI.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from . import storage

log = logging.getLogger("tiktok")

API_BASE = "https://open.tiktokapis.com/v2"


def publish_to_tiktok(video_path: str, title: str) -> tuple[bool, str]:
    """Publie une vidéo. Retourne (succès, message)."""
    token = storage.get_config("tiktok_access_token")
    if not token:
        return False, "Token TikTok manquant : renseignez-le dans l'onglet Configuration."

    path = Path(video_path)
    if not path.exists():
        return False, "Fichier vidéo introuvable."

    video_bytes = path.read_bytes()
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=120) as client:
            # 1. Initialisation de l'upload (mode direct post)
            init = client.post(
                f"{API_BASE}/post/publish/video/init/",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "post_info": {
                        "title": title or "Clip Twitch 😂 #twitch #clip #fyp",
                        "privacy_level": "SELF_ONLY",  # passer à PUBLIC_TO_EVERYONE une fois l'app approuvée
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": len(video_bytes),
                        "chunk_size": len(video_bytes),
                        "total_chunk_count": 1,
                    },
                },
            )
            data = init.json()
            if init.status_code != 200 or data.get("error", {}).get("code") not in ("ok", None):
                return False, f"Init TikTok refusée : {data.get('error', data)}"

            upload_url = data["data"]["upload_url"]

            # 2. Upload de la vidéo
            upload = client.put(
                upload_url,
                content=video_bytes,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes 0-{len(video_bytes) - 1}/{len(video_bytes)}",
                },
            )
            if upload.status_code not in (200, 201):
                return False, f"Upload TikTok échoué (HTTP {upload.status_code})."

        log.info("Vidéo %s envoyée à TikTok", path.name)
        return True, "Vidéo envoyée ! TikTok la traite (visible dans l'app d'ici quelques minutes)."

    except httpx.HTTPError as exc:
        return False, f"Erreur réseau TikTok : {exc}"
