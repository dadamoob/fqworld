"""
Couche de stockage partagée entre l'UI (app.py) et le Cerveau (agent/brain.py).

Les deux processus (voire deux conteneurs Docker) lisent/écrivent la même
base SQLite (data/agent.db, mode WAL => accès concurrent sûr).
C'est CE fichier qui permet à l'utilisateur de tout piloter depuis l'UI
sans jamais toucher au code.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get("FQ_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
CLIPS_DIR = DATA_DIR / "clips"
DB_PATH = DATA_DIR / "agent.db"

# Statuts possibles d'un clip dans la bibliothèque
CLIP_READY = "Prêt"
CLIP_POSTED = "Posté sur TikTok"
CLIP_FAILED = "Échec"
CLIP_REJECTED = "Rejeté par l'IA"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS streamers (
    username     TEXT PRIMARY KEY,
    added_at     REAL NOT NULL,
    is_live      INTEGER NOT NULL DEFAULT 0,
    stream_title TEXT DEFAULT '',
    last_checked REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS clips (
    id          TEXT PRIMARY KEY,
    streamer    TEXT NOT NULL,
    title       TEXT DEFAULT '',
    path        TEXT NOT NULL,
    status      TEXT NOT NULL,
    transcript  TEXT DEFAULT '',
    humor_score REAL DEFAULT 0,
    error       TEXT DEFAULT '',
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Clés de configuration éditables dans l'onglet "Configuration" de l'UI.
CONFIG_KEYS = {
    "twitch_client_id":     {"label": "Twitch Client ID", "secret": False},
    "twitch_client_secret": {"label": "Twitch Client Secret", "secret": True},
    "openai_api_key":       {"label": "Clé API OpenAI (Whisper + LLM)", "secret": True},
    "tiktok_access_token":  {"label": "TikTok Access Token", "secret": True},
    "laugh_threshold":      {"label": "Seuil de pic de rires (x la normale)", "secret": False, "default": "4"},
    "clip_duration":        {"label": "Durée des clips (secondes)", "secret": False, "default": "30"},
    "auto_post":            {"label": "Publication TikTok automatique (true/false)", "secret": False, "default": "false"},
}


def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA journal_mode=WAL;")
        con.executescript(_SCHEMA)


@contextmanager
def _db():
    _init_db()
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------- streamers

def add_streamer(username: str) -> None:
    username = username.strip().lstrip("@").lower()
    if not username:
        return
    with _db() as con:
        con.execute(
            "INSERT OR IGNORE INTO streamers (username, added_at) VALUES (?, ?)",
            (username, time.time()),
        )


def remove_streamer(username: str) -> None:
    with _db() as con:
        con.execute("DELETE FROM streamers WHERE username = ?", (username,))


def list_streamers() -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT * FROM streamers ORDER BY added_at").fetchall()
    return [dict(r) for r in rows]


def set_live_status(username: str, is_live: bool, stream_title: str = "") -> None:
    with _db() as con:
        con.execute(
            "UPDATE streamers SET is_live = ?, stream_title = ?, last_checked = ? WHERE username = ?",
            (int(is_live), stream_title, time.time(), username),
        )


# -------------------------------------------------------------------- clips

def add_clip(streamer: str, path: str, title: str, status: str,
             transcript: str = "", humor_score: float = 0.0, error: str = "") -> str:
    clip_id = uuid.uuid4().hex[:12]
    with _db() as con:
        con.execute(
            "INSERT INTO clips (id, streamer, title, path, status, transcript, humor_score, error, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (clip_id, streamer, title, path, status, transcript, humor_score, error, time.time()),
        )
    return clip_id


def list_clips() -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT * FROM clips ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_clip_status(clip_id: str, status: str, error: str = "") -> None:
    with _db() as con:
        con.execute("UPDATE clips SET status = ?, error = ? WHERE id = ?", (status, error, clip_id))


def delete_clip(clip_id: str) -> None:
    with _db() as con:
        row = con.execute("SELECT path FROM clips WHERE id = ?", (clip_id,)).fetchone()
        con.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
    if row and row["path"]:
        Path(row["path"]).unlink(missing_ok=True)


# ------------------------------------------------------------------- config

def get_config(key: str, default: str | None = None) -> str | None:
    with _db() as con:
        row = con.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    if row is not None:
        return row["value"]
    meta = CONFIG_KEYS.get(key, {})
    return meta.get("default", default)


def set_config(key: str, value: str) -> None:
    with _db() as con:
        con.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_all_config() -> dict[str, str]:
    with _db() as con:
        rows = con.execute("SELECT key, value FROM config").fetchall()
    cfg = {k: meta.get("default", "") for k, meta in CONFIG_KEYS.items()}
    cfg.update({r["key"]: r["value"] for r in rows})
    return cfg
