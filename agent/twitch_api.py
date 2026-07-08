"""
Client Twitch Helix minimal, partagé entre l'UI (liste des rediffusions)
et le Cerveau (statut live). Token applicatif auto-renouvelé en mémoire.
"""

from __future__ import annotations

import re
import time

import httpx

from . import storage

_token: str | None = None
_token_expiry = 0.0


class TwitchConfigError(Exception):
    """Problème de configuration Twitch, avec un message clair pour l'UI."""


class TwitchKeysMissing(TwitchConfigError):
    """Levée quand les clés Twitch ne sont pas encore configurées dans l'UI."""


def _get_token() -> str:
    global _token, _token_expiry
    client_id = storage.get_config("twitch_client_id")
    secret = storage.get_config("twitch_client_secret")
    if not client_id or not secret:
        raise TwitchKeysMissing(
            "Clés Twitch manquantes : ajoutez-les dans l'onglet Configuration."
        )
    if client_id == secret:
        raise TwitchConfigError(
            "Le Client ID et le Client Secret sont identiques : vous avez "
            "probablement collé deux fois le Client ID. Sur la page de votre "
            "application Twitch, cliquez « New Secret » pour générer le "
            "Client Secret (une clé différente), puis collez-le dans l'onglet "
            "Configuration."
        )
    if _token and time.time() < _token_expiry - 60:
        return _token
    # credentials dans le CORPS de la requête (jamais dans l'URL -> pas de
    # secret dans les messages d'erreur ni les logs)
    resp = httpx.post(
        "https://id.twitch.tv/oauth2/token",
        data={"client_id": client_id, "client_secret": secret,
              "grant_type": "client_credentials"},
        timeout=15,
    )
    if resp.status_code in (400, 401, 403):
        raise TwitchConfigError(
            "Twitch a refusé vos clés (Client ID ou Client Secret invalide). "
            "Vérifiez-les dans l'onglet Configuration — au besoin, générez un "
            "nouveau secret avec « New Secret » sur la page de votre "
            "application Twitch (dev.twitch.tv/console/apps)."
        )
    resp.raise_for_status()
    data = resp.json()
    _token = data["access_token"]
    _token_expiry = time.time() + data.get("expires_in", 3600)
    return _token


def _get(path: str, params) -> dict:
    global _token
    headers = {"Client-ID": storage.get_config("twitch_client_id"),
               "Authorization": f"Bearer {_get_token()}"}
    resp = httpx.get(f"https://api.twitch.tv/helix/{path}",
                     params=params, headers=headers, timeout=15)
    if resp.status_code == 401:  # token révoqué -> on force un renouvellement
        _token = None
        headers["Authorization"] = f"Bearer {_get_token()}"
        resp = httpx.get(f"https://api.twitch.tv/helix/{path}",
                         params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_live_streams(usernames: list[str]) -> dict[str, str]:
    """Retourne {username: titre_du_stream} pour ceux qui sont EN LIVE."""
    if not usernames:
        return {}
    data = _get("streams", [("user_login", u) for u in usernames[:100]])
    return {s["user_login"].lower(): s.get("title", "") for s in data.get("data", [])}


def get_user_id(login: str) -> str | None:
    data = _get("users", {"login": login})
    users = data.get("data", [])
    return users[0]["id"] if users else None


def _parse_duration(text: str) -> int:
    """'3h4m33s' -> secondes."""
    total = 0
    for value, unit in re.findall(r"(\d+)([hms])", text):
        total += int(value) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total


def get_recent_vods(login: str, limit: int = 5) -> list[dict]:
    """Dernières rediffusions (VOD) d'un streamer, la plus récente d'abord."""
    user_id = get_user_id(login)
    if user_id is None:
        return []
    data = _get("videos", {"user_id": user_id, "type": "archive", "first": limit})
    return [
        {
            "id": v["id"],
            "url": v["url"],
            "title": v.get("title", "Sans titre"),
            "duration_s": _parse_duration(v.get("duration", "0s")),
            "created_at": v.get("created_at", ""),
        }
        for v in data.get("data", [])
    ]
