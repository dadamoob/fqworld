# 🎬 FQWorld — Agent autonome Twitch → TikTok

Un agent qui surveille vos streamers Twitch préférés, détecte automatiquement
les moments drôles (en live via le chat, ou dans les **rediffusions** via
l'analyse audio) avec validation par IA, monte des clips au format TikTok
(9:16) et les publie — le tout piloté depuis **une interface web
ultra-simple**, sans jamais toucher au code.

## ⚡ Installation en 3 étapes (aucune compétence requise)

1. **Installez [Docker Desktop](https://www.docker.com/products/docker-desktop/)**
   (gratuit) et lancez-le une fois.
2. **Téléchargez ce projet** : bouton vert **Code → Download ZIP** en haut de
   cette page, puis décompressez le dossier (lisez `COMMENCEZ-ICI.txt`).
3. **Double-cliquez sur `install.bat`** (Windows) ou lancez `bash install.sh`
   (Mac/Linux). L'installation **crée un raccourci « FQWorld » sur votre
   Bureau** et ouvre l'interface sur http://localhost:8501. 🎉

**Au quotidien : un double-clic sur le raccourci Bureau suffit** — il démarre
même Docker s'il est fermé, puis ouvre l'interface. Pour arrêter : raccourci
« Arrêter FQWorld » (Windows) ou `bash stop.sh` (clips et config conservés).

Ensuite, l'onglet **⚙️ Configuration** de l'interface vous guide pas à pas
(liens directs inclus) pour récupérer vos clés Twitch/OpenAI/TikTok.

## 🖥️ L'interface (Streamlit)

| Onglet | Ce qu'on y fait |
|---|---|
| 📡 **Dashboard** | Voir les streamers suivis (🔴 En live / ⚫ Hors ligne), en ajouter un avec juste son pseudo |
| 📼 **Rediffusions** | Choisir une VOD d'un streamer : l'IA l'analyse et en tire 1 à 5 clips, sans attendre un live |
| 🎞️ **Bibliothèque de Clips** | Galerie des clips générés, statut (Prêt / Posté sur TikTok / Échec / Rejeté par l'IA), publication manuelle ou téléchargement |
| ⚙️ **Configuration** | Guides pas à pas avec liens directs pour chaque clé API (Twitch, OpenAI, TikTok) + réglages de sensibilité |

## 🧠 Le moteur (sous le capot)

```
   MODE LIVE                              MODE REDIFFUSION (VOD)
Chat Twitch (IRC anonyme)              Piste audio de la VOD (streamlink)
        │                                        │
 Pic de "LUL/MDR/KEKW" ?               Pics de volume (cris, fous rires)
        │  oui                                   │
Extraction des 30 dernières s          Téléchargement des 30 s concernées
(buffer circulaire streamlink)         (seek HLS, pas toute la vidéo)
        └──────────────┬─────────────────────────┘
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
├── COMMENCEZ-ICI.txt         # 📖 Le premier fichier à lire après avoir dézippé
├── app.py                    # 🖥️ Interface web Streamlit (le SEUL point de contact utilisateur)
├── install.bat / install.sh  # ⚡ Installation en un double-clic + raccourcis Bureau
├── FQWorld.bat / FQWorld.sh  # ▶️ Lanceur quotidien (visé par le raccourci Bureau)
├── stop.bat / stop.sh        # ⏹️ Arrêt propre
├── agent/
│   ├── brain.py              # 🧠 Orchestrateur : boucle de surveillance + pipeline des clips
│   ├── chat_monitor.py       # 👂 Lecture du chat Twitch (IRC) + détection des pics de rires
│   ├── vod_hunter.py         # 📼 Analyse des rediffusions : pics audio + clips
│   ├── twitch_api.py         # 🔌 Client Twitch Helix partagé (live, VOD)
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
