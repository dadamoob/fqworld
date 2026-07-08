# 🎬 FQWorld — Agent autonome Twitch → TikTok

Un agent qui surveille vos streamers Twitch préférés, détecte automatiquement
les moments drôles (pics de rires du chat + validation par IA), monte des clips
au format TikTok (9:16) et les publie — le tout piloté depuis **une interface
web ultra-simple**, sans jamais toucher au code.

## 🖥️ L'interface (Streamlit)

| Onglet | Ce qu'on y fait |
|---|---|
| 📡 **Dashboard** | Voir les streamers suivis (🔴 En live / ⚫ Hors ligne), en ajouter un avec juste son pseudo |
| 🎞️ **Bibliothèque de Clips** | Galerie des clips générés, statut (Prêt / Posté sur TikTok / Échec / Rejeté par l'IA), bouton de publication manuelle |
| ⚙️ **Configuration** | Clés API (Twitch, OpenAI, TikTok) et réglages de sensibilité, sans ouvrir un seul fichier |

## 🧠 Le moteur (sous le capot)

```
Chat Twitch (IRC anonyme)          Flux vidéo (streamlink)
        │                                  │
   Pic de "LUL/MDR/KEKW" ?          Buffer circulaire 3 min
        │  oui                             │
        └──────► Extraction des 30 dernières secondes (FFmpeg)
                        │
                 Whisper (transcription) + LLM (verdict "drôle ?")
                        │  validé
                 Recadrage 9:16 → 1080x1920 (FFmpeg)
                        │
                 Bibliothèque de clips ──► TikTok (auto ou manuel)
```

L'UI et le Cerveau sont **deux processus indépendants** qui communiquent via
une base SQLite partagée (`data/agent.db`) : ajoutez un streamer dans l'UI,
le Cerveau le prend en compte à son prochain cycle (~60 s).

## 🚀 Lancement en un clic (Docker)

```bash
docker compose up --build -d
```

Puis ouvrez **http://localhost:8501**. C'est tout — même commande en local ou
sur un VPS/AWS (ouvrez le port 8501 ou mettez un reverse proxy devant).

## 🧪 Lancement manuel (sans Docker, pour développer)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# FFmpeg requis : sudo apt install ffmpeg  (ou brew install ffmpeg)

# Terminal 1 — l'interface
streamlit run app.py

# Terminal 2 — le cerveau
python -m agent.brain
```

## 🔑 Clés API nécessaires (à coller dans l'onglet Configuration)

- **Twitch** : https://dev.twitch.tv/console/apps → créer une app → Client ID + Secret
  (sert uniquement à savoir qui est en live ; la lecture du chat est anonyme)
- **OpenAI** : https://platform.openai.com/api-keys (Whisper + gpt-4o-mini)
- **TikTok** : https://developers.tiktok.com → Content Posting API (scope `video.publish`)

Sans clé OpenAI, l'agent fonctionne quand même : les clips sont gardés sur
simple pic de chat, sans filtre IA. Sans token TikTok, les clips restent
en « Prêt » dans la bibliothèque.

## 📁 Structure du projet

```
fqworld/
├── app.py                    # 🖥️ Interface web Streamlit (le SEUL point de contact utilisateur)
├── agent/
│   ├── brain.py              # 🧠 Orchestrateur : boucle de surveillance + pipeline des clips
│   ├── chat_monitor.py       # 👂 Lecture du chat Twitch (IRC) + détection des pics de rires
│   ├── clipper.py            # ✂️ Buffer vidéo streamlink + montage FFmpeg 9:16
│   ├── humor_ai.py           # 🤖 Whisper (transcription) + LLM (verdict humour)
│   ├── tiktok_publisher.py   # 🚀 Publication via la Content Posting API TikTok
│   └── storage.py            # 🗄️ Base SQLite partagée UI ↔ Cerveau
├── data/                     # état persistant : agent.db, clips/, buffers/ (volume Docker)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## ⚠️ À savoir

- La publication TikTok nécessite une app **approuvée** par TikTok pour poster
  en public ; en attendant, les posts partent en `SELF_ONLY` (visibles par vous seul).
- Respectez les droits des streamers : clipper et republier leur contenu
  nécessite leur accord.
