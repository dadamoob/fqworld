"""
FQWorld — Interface Web ultra-simple de l'agent Twitch → TikTok.

Lancement :  streamlit run app.py  (ou double-clic sur install.bat / install.sh)
L'utilisateur pilote TOUT depuis ici (streamers, clips, rediffusions, clés API),
le moteur technique (agent/brain.py) tourne en arrière-plan et
communique via la base SQLite partagée (agent/storage.py).
"""

import time
from pathlib import Path

import httpx
import streamlit as st

from agent import storage, twitch_api
from agent.tiktok_publisher import publish_to_tiktok

_version_file = Path(__file__).parent / "VERSION"
VERSION = _version_file.read_text().strip() if _version_file.exists() else "dev"


@st.cache_data(ttl=3600, show_spinner=False)
def latest_version() -> str | None:
    """Vérifie (au plus 1x/heure) si une nouvelle version est publiée sur GitHub."""
    try:
        r = httpx.get("https://raw.githubusercontent.com/dadamoob/fqworld/main/VERSION",
                      timeout=4)
        if r.status_code == 200:
            return r.text.strip()
    except Exception:
        pass
    return None

st.set_page_config(page_title="FQWorld", page_icon="🎬", layout="wide")

# Habillage « logiciel » : éléments techniques masqués + design FQWorld
st.markdown("""
<style>
  #MainMenu, footer,
  [data-testid="stAppDeployButton"],
  [data-testid="stToolbar"],
  [data-testid="stDecoration"] { visibility: hidden; height: 0; }
  .block-container { padding-top: 2.2rem; max-width: 1250px; }

  /* Titre en dégradé Twitch -> TikTok */
  h1 {
    background: linear-gradient(90deg, #9146FF 0%, #FF2D74 70%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800;
  }

  /* Cartes (statistiques et conteneurs) */
  [data-testid="stMetric"] {
    background: linear-gradient(160deg, #1f1f23 0%, #17171a 100%);
    border: 1px solid #2e2e35; border-radius: 16px; padding: 14px 18px;
  }
  [data-testid="stMetricValue"] { font-weight: 700; }
  [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 16px; }

  /* Boutons primaires en dégradé */
  .stButton > button[kind="primary"], .stFormSubmitButton > button {
    background: linear-gradient(90deg, #9146FF, #FF2D74);
    border: none; color: white; font-weight: 600;
  }
  .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
    filter: brightness(1.15);
  }

  /* Vidéos et onglets adoucis */
  video { border-radius: 14px; }
  button[data-baseweb="tab"] { font-size: 1.02rem; }
</style>
""", unsafe_allow_html=True)

st.title("🎬 FQWorld — Agent Twitch → TikTok")
st.caption("Détection automatique des moments drôles (en live OU dans les rediffusions), "
           "montage 9:16 et publication TikTok.")


@st.fragment(run_every="15s")
def engine_status() -> None:
    """Indicateur temps réel : le moteur (cerveau) tourne-t-il vraiment ?"""
    heartbeat = storage.get_config("brain_heartbeat")
    alive = False
    if heartbeat:
        try:
            alive = time.time() - float(heartbeat) < 150  # 2 cycles + marge
        except ValueError:
            alive = False
    if alive:
        st.caption("🧠 Moteur : 🟢 **actif** — surveillance en cours, "
                   "statuts mis à jour automatiquement")
    else:
        st.error("🔴 **Le moteur est arrêté** : l'interface fonctionne mais rien n'est "
                 "surveillé. Lancez FQWorld via le raccourci Bureau "
                 "(ou `docker compose up -d`), ce bandeau passera au vert tout seul.")


engine_status()

_latest = latest_version()
if _latest and _latest != VERSION:
    st.info(f"🔄 **Nouvelle version {_latest} disponible** (vous êtes en v{VERSION}). "
            "Pour mettre à jour en un clic : double-cliquez sur `update.bat` "
            "(Windows) ou lancez `bash update.sh` (Mac/Linux) — vos clips et "
            "votre configuration sont conservés.")

config = storage.get_all_config()
twitch_ok = bool(config.get("twitch_client_id")) and bool(config.get("twitch_client_secret"))
openai_ok = bool(config.get("openai_api_key"))
tiktok_ok = bool(config.get("tiktok_access_token"))

# Bandeau d'accueil pour les nouveaux utilisateurs
if not twitch_ok:
    st.warning(
        "👋 **Bienvenue ! Il ne reste qu'une étape avant de démarrer :** "
        "ouvrez l'onglet **⚙️ Configuration** ci-dessous et suivez le guide "
        "(2 minutes, tous les liens sont fournis). Sans les clés Twitch, "
        "l'agent ne peut pas savoir qui est en live."
    )

tab_dashboard, tab_vod, tab_library, tab_config = st.tabs(
    ["📡 Dashboard", "📼 Rediffusions", "🎞️ Bibliothèque de Clips", "⚙️ Configuration"]
)

# ════════════════════════════════════════════════ Onglet 1 : Dashboard
with tab_dashboard:

    @st.fragment(run_every="15s")
    def stats_row() -> None:
        streamers_all = storage.list_streamers()
        clips_all = storage.list_clips()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("👥 Streamers suivis", len(streamers_all))
        col2.metric("🔴 En live", sum(1 for s in streamers_all if s["is_live"]))
        col3.metric("🎬 Clips prêts",
                    sum(1 for c in clips_all if c["status"] == storage.CLIP_READY))
        col4.metric("🚀 Publiés TikTok",
                    sum(1 for c in clips_all if c["status"] == storage.CLIP_POSTED))

    stats_row()
    st.divider()
    st.subheader("Streamers suivis en direct")
    st.caption("Ajoutez un pseudo : dès que le streamer passe en live, l'agent écoute son chat "
               "et clippe automatiquement les moments où tout le monde rit.")

    with st.form("add_streamer_form", clear_on_submit=True):
        col_input, col_btn = st.columns([4, 1])
        pseudo = col_input.text_input(
            "Pseudo Twitch", placeholder="ex : squeezie, kameto… (juste le pseudo, pas l'URL)",
            label_visibility="collapsed",
        )
        submitted = col_btn.form_submit_button("➕ Ajouter", use_container_width=True)
        if submitted and pseudo.strip():
            storage.add_streamer(pseudo)
            st.toast(f"✅ {pseudo.strip()} ajouté ! Le cerveau le surveillera d'ici ~1 minute.")

    @st.fragment(run_every="10s")
    def streamer_list() -> None:
        streamers = storage.list_streamers()
        if not streamers:
            st.info("Aucun streamer suivi pour l'instant. Ajoutez un pseudo ci-dessus 👆")
            return
        for s in streamers:
            col_name, col_status, col_title, col_del = st.columns([2, 1, 3, 1])
            col_name.markdown(f"**{s['username']}**")
            if s["is_live"]:
                col_status.markdown("🔴 **EN LIVE**")
            else:
                col_status.markdown("⚫ Hors ligne")
            col_title.caption(s["stream_title"] or "—")
            if col_del.button("🗑️ Retirer", key=f"del_{s['username']}"):
                storage.remove_streamer(s["username"])
                st.rerun()
        st.caption("✨ Statuts mis à jour automatiquement (moteur : ~60 s, affichage : 10 s).")

    streamer_list()

    st.divider()
    st.subheader("📰 Journal d'activité")

    @st.fragment(run_every="10s")
    def activity_feed() -> None:
        events = storage.list_events(12)
        if not events:
            st.caption("L'activité de l'agent s'affichera ici : passages en live, "
                       "pics de rires, clips créés, publications TikTok…")
            return
        for e in events:
            when = time.strftime("%d/%m %H:%M", time.localtime(e["ts"]))
            st.markdown(f"`{when}` — {e['message']}")

    activity_feed()

# ═══════════════════════════════════════════ Onglet 2 : Rediffusions
with tab_vod:
    st.subheader("Créer des clips depuis les rediffusions (VOD)")
    st.caption("Pas besoin d'attendre un live ! L'IA écoute la rediffusion, repère les moments "
               "les plus intenses (cris, éclats de rire) et en tire des clips TikTok.")

    if not twitch_ok:
        st.info("⚙️ Configurez d'abord vos clés Twitch dans l'onglet **Configuration** "
                "pour pouvoir lister les rediffusions.")
    else:
        followed = [s["username"] for s in storage.list_streamers()]
        col_sel, col_other = st.columns([2, 2])
        choice = col_sel.selectbox(
            "Streamer", options=followed + ["✏️ Autre pseudo…"] if followed else ["✏️ Autre pseudo…"],
        )
        if choice == "✏️ Autre pseudo…":
            target = col_other.text_input("Pseudo Twitch", placeholder="ex : squeezie")
        else:
            target = choice

        if st.button("🔍 Voir ses dernières rediffusions", disabled=not (target or "").strip()):
            try:
                st.session_state["vods"] = twitch_api.get_recent_vods(target.strip().lower())
                st.session_state["vods_streamer"] = target.strip().lower()
                if not st.session_state["vods"]:
                    st.warning("Aucune rediffusion trouvée : le streamer doit activer "
                               "« Enregistrer les diffusions » dans ses paramètres Twitch.")
            except twitch_api.TwitchConfigError as exc:
                st.error(f"⚙️ {exc}")
            except Exception as exc:
                st.error(f"Impossible de récupérer les rediffusions : {exc}")

        vods = st.session_state.get("vods") or []
        if vods:
            def _label(v):
                hours, minutes = int(v["duration_s"] // 3600), int(v["duration_s"] % 3600 // 60)
                date = (v["created_at"] or "")[:10]
                return f"{v['title'][:60]} — {date} ({hours}h{minutes:02d})"

            selected = st.selectbox("Choisissez la rediffusion à analyser",
                                    options=vods, format_func=_label)
            clips_wanted = st.slider("Nombre de clips à en tirer", 1, 5, 3)
            estimated = max(2, int(selected["duration_s"] / 60 / 8))
            st.caption(f"⏱️ Durée estimée de l'analyse : ~{estimated} min "
                       "(l'agent streame l'audio sans télécharger toute la vidéo).")

            if st.button("🚀 Lancer l'analyse", type="primary"):
                storage.add_vod_job(
                    streamer=st.session_state["vods_streamer"],
                    vod_id=selected["id"], vod_url=selected["url"],
                    vod_title=selected["title"],
                    vod_duration=selected["duration_s"],
                    clips_wanted=clips_wanted,
                )
                st.toast("📼 Analyse programmée ! Le cerveau s'en occupe d'ici ~1 minute.")
                st.session_state.pop("vods", None)
                st.rerun()

    @st.fragment(run_every="10s")
    def vod_jobs_list() -> None:
        jobs = storage.list_vod_jobs()
        if not jobs:
            return
        st.divider()
        st.markdown("##### Analyses en cours et terminées")
        icons = {storage.JOB_PENDING: "⏳", storage.JOB_RUNNING: "🔍",
                 storage.JOB_DONE: "✅", storage.JOB_FAILED: "🔴"}
        for job in jobs:
            with st.container(border=True):
                col_info, col_state, col_del = st.columns([4, 2, 1])
                col_info.markdown(f"**{job['streamer']}** — {job['vod_title'][:70]}")
                col_state.markdown(f"{icons.get(job['status'], '')} {job['status']}"
                                   + (f" · {job['clips_found']} clip(s) validé(s)"
                                      if job["status"] == storage.JOB_DONE else ""))
                if job["status"] == storage.JOB_RUNNING:
                    st.progress(min(1.0, float(job["progress"] or 0)))
                if job["error"]:
                    st.caption(f"⚠️ {job['error']}")
                if col_del.button("🗑️", key=f"job_{job['id']}", help="Retirer de la liste"):
                    storage.delete_vod_job(job["id"])
                    st.rerun()
        st.caption("✨ Progression mise à jour automatiquement. Les clips validés "
                   "apparaissent dans l'onglet 🎞️ Bibliothèque de Clips.")

    vod_jobs_list()

# ════════════════════════════════════ Onglet 3 : Bibliothèque de Clips
with tab_library:
    st.subheader("Clips humoristiques générés")

    clips = storage.list_clips()
    if not clips:
        st.info("Aucun clip pour l'instant. Deux façons d'en obtenir : suivre un streamer "
                "en live (📡 Dashboard) ou analyser une rediffusion (📼 Rediffusions). 🍿")
    else:
        badges = {
            storage.CLIP_READY: "🟢 Prêt",
            storage.CLIP_POSTED: "🚀 Posté sur TikTok",
            storage.CLIP_FAILED: "🔴 Échec",
            storage.CLIP_REJECTED: "🟡 Rejeté par l'IA",
        }
        # Pagination : 12 clips affichés, le reste sur demande
        if len(clips) > 12 and not st.toggle(
                f"Afficher les {len(clips)} clips (sinon les 12 plus récents)"):
            clips = clips[:12]
        # Galerie : 3 clips par ligne
        for row_start in range(0, len(clips), 3):
            cols = st.columns(3)
            for col, clip in zip(cols, clips[row_start:row_start + 3]):
                with col, st.container(border=True):
                    st.markdown(f"**{clip['title'] or 'Clip sans titre'}**")
                    st.caption(
                        f"{clip['streamer']} · "
                        f"{time.strftime('%d/%m/%Y %H:%M', time.localtime(clip['created_at']))} · "
                        f"score humour : {clip['humor_score']:.0%}"
                    )
                    video_path = Path(clip["path"])
                    if video_path.exists():
                        st.video(str(video_path))
                    else:
                        st.warning("Fichier vidéo introuvable")

                    st.markdown(badges.get(clip["status"], clip["status"]))
                    if clip["error"]:
                        st.caption(f"⚠️ {clip['error']}")
                    if clip["transcript"]:
                        with st.expander("📝 Transcription"):
                            st.write(clip["transcript"])

                    col_pub, col_dl, col_del = st.columns(3)
                    if clip["status"] != storage.CLIP_POSTED:
                        if col_pub.button("🚀 Publier", key=f"pub_{clip['id']}",
                                          use_container_width=True,
                                          help="Publier maintenant sur TikTok"):
                            with st.spinner("Publication sur TikTok…"):
                                ok, message = publish_to_tiktok(clip["path"], clip["title"])
                            if ok:
                                storage.update_clip_status(clip["id"], storage.CLIP_POSTED)
                                st.toast("🚀 Publié sur TikTok !")
                            else:
                                storage.update_clip_status(clip["id"], storage.CLIP_FAILED, error=message)
                                st.toast(f"❌ Échec : {message}")
                            st.rerun()
                    if video_path.exists():
                        with open(video_path, "rb") as f:
                            col_dl.download_button(
                                "⬇️ Télécharger", data=f, file_name=video_path.name,
                                mime="video/mp4", key=f"dl_{clip['id']}",
                                use_container_width=True,
                                help="Récupérer le fichier pour le poster à la main",
                            )
                    if col_del.button("🗑️ Suppr.", key=f"rm_{clip['id']}", use_container_width=True):
                        storage.delete_clip(clip["id"])
                        st.rerun()

# ═══════════════════════════════════════════ Onglet 4 : Configuration
with tab_config:
    st.subheader("Configuration guidée")
    st.caption("Tous les liens sont là, il suffit de copier-coller. Les clés sont stockées "
               "uniquement chez vous, dans `data/agent.db` — jamais envoyées ailleurs.")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Twitch", "✅ Configuré" if twitch_ok else "❌ À faire")
    col_b.metric("OpenAI (IA)", "✅ Configuré" if openai_ok else "⭕ Optionnel")
    col_c.metric("TikTok", "✅ Configuré" if tiktok_ok else "⭕ Optionnel")

    # ------------------------------------------------------------ TWITCH
    with st.container(border=True):
        st.markdown("### 1️⃣ Twitch — obligatoire " + ("✅" if twitch_ok else "❌"))
        st.markdown("Sert à savoir qui est en live et à lister les rediffusions. **Gratuit.**")
        col_link1, col_link2 = st.columns(2)
        col_link1.link_button("🔑 Créer mon application Twitch",
                              "https://dev.twitch.tv/console/apps/create",
                              use_container_width=True)
        col_link2.link_button("🛡️ Activer la 2FA Twitch (requis avant)",
                              "https://www.twitch.tv/settings/security",
                              use_container_width=True)
        with st.expander("📖 Guide pas à pas (2 minutes)"):
            st.markdown(
                "1. **Activez d'abord la double authentification (2FA)** sur votre compte "
                "Twitch via le bouton 🛡️ ci-dessus (Twitch l'exige — erreur "
                "*« two factor auth »* sinon). Il faut un numéro de téléphone.\n"
                "2. Cliquez sur **🔑 Créer mon application Twitch** :\n"
                "   - *Name* : ce que vous voulez (ex : `fqworld`)\n"
                "   - *OAuth Redirect URLs* : `http://localhost`\n"
                "   - *Category* : **Other** → **Create**\n"
                "3. Sur la page de l'application : copiez le **Client ID** dans le champ "
                "ci-dessous, puis cliquez **New Secret** et copiez le **Client Secret**.\n"
                "4. Cliquez sur **💾 Enregistrer** tout en bas."
            )
        twitch_client_id = st.text_input("Twitch Client ID",
                                         value=config.get("twitch_client_id", ""))
        twitch_client_secret = st.text_input("Twitch Client Secret", type="password",
                                             value=config.get("twitch_client_secret", ""))
        if twitch_client_id and twitch_client_id == twitch_client_secret:
            st.error("⚠️ Le Client ID et le Client Secret sont **identiques** : "
                     "vous avez collé deux fois le Client ID ! Le Client Secret est "
                     "une clé **différente** : sur la page de votre application "
                     "Twitch, cliquez **New Secret**, copiez la clé générée et "
                     "collez-la dans le champ Client Secret.")

    # ------------------------------------------------------------ OPENAI
    with st.container(border=True):
        st.markdown("### 2️⃣ OpenAI — recommandé " + ("✅" if openai_ok else "⭕"))
        st.markdown("Active le **filtre IA** : Whisper transcrit le clip et un LLM vérifie "
                    "qu'il est vraiment drôle avant de le garder. Sans clé, tous les pics "
                    "sont conservés et vous triez à la main.")
        st.link_button("🔑 Créer ma clé API OpenAI",
                       "https://platform.openai.com/api-keys")
        with st.expander("📖 Guide pas à pas (1 minute)"):
            st.markdown(
                "1. Cliquez sur le bouton ci-dessus et connectez-vous (ou créez un compte).\n"
                "2. Cliquez **Create new secret key** → donnez un nom → **Create**.\n"
                "3. Copiez la clé (elle commence par `sk-`) dans le champ ci-dessous.\n"
                "4. 💳 Ajoutez quelques euros de crédit dans *Settings → Billing* "
                "(comptez ~0,01 € par clip analysé).\n"
                "5. Cliquez sur **💾 Enregistrer** tout en bas."
            )
        openai_api_key = st.text_input("Clé API OpenAI (commence par sk-)", type="password",
                                       value=config.get("openai_api_key", ""))

    # ------------------------------------------------------------ TIKTOK
    with st.container(border=True):
        st.markdown("### 3️⃣ TikTok — pour la publication automatique " + ("✅" if tiktok_ok else "⭕"))
        st.markdown("Sans ce token, les clips restent en **🟢 Prêt** : vous pouvez les "
                    "**⬇️ Télécharger** depuis la bibliothèque et les poster à la main — "
                    "c'est la solution la plus simple pour débuter.")
        st.link_button("🔑 Portail développeur TikTok",
                       "https://developers.tiktok.com/apps/")
        with st.expander("📖 Guide pas à pas (le plus long — faites-le en dernier)"):
            st.markdown(
                "1. Créez un compte développeur via le bouton ci-dessus, puis **Manage apps → "
                "Connect an app**.\n"
                "2. Ajoutez le produit **Content Posting API** et demandez le scope "
                "`video.publish`.\n"
                "3. ⚠️ TikTok doit **approuver** votre application (quelques jours). "
                "En attendant l'approbation, les vidéos publiées ne sont visibles que "
                "par vous (mode `SELF_ONLY`).\n"
                "4. Une fois l'app validée, générez un **access token** OAuth et collez-le "
                "ci-dessous.\n"
                "5. Cliquez sur **💾 Enregistrer** tout en bas."
            )
        tiktok_access_token = st.text_input("TikTok Access Token", type="password",
                                            value=config.get("tiktok_access_token", ""))

    # ----------------------------------------------------------- RÉGLAGES
    with st.container(border=True):
        st.markdown("### 🎛️ Réglages de l'agent")
        laugh_threshold = st.slider(
            "Sensibilité en live : pic de rires requis (× l'activité normale du chat)",
            min_value=2, max_value=10, value=int(float(config.get("laugh_threshold", "4"))),
            help="Plus bas = plus de clips (mais plus de déchet). 2 = très sensible, 10 = seulement les gros fous rires.",
        )
        clip_duration = st.slider(
            "Durée des clips (secondes)",
            min_value=15, max_value=60, value=int(float(config.get("clip_duration", "30"))),
        )
        auto_post = st.toggle(
            "Publier automatiquement sur TikTok (sinon les clips attendent en « Prêt »)",
            value=config.get("auto_post", "false") == "true",
        )
        subtitles = st.toggle(
            "Sous-titres automatiques incrustés sur les clips (style TikTok, via Whisper)",
            value=config.get("subtitles", "true") == "true",
        )
        default_hashtags = st.text_input(
            "Hashtags ajoutés aux titres des clips",
            value=config.get("default_hashtags", "#twitch #clip #fyp"),
        )
        languages = {"fr": "Français", "en": "Anglais", "es": "Espagnol", "de": "Allemand"}
        current_lang = config.get("language", "fr")
        language = st.selectbox(
            "Langue parlée dans les streams (pour la transcription)",
            options=list(languages),
            index=list(languages).index(current_lang) if current_lang in languages else 0,
            format_func=languages.get,
        )

    if st.button("💾 Enregistrer la configuration", type="primary", use_container_width=True):
        storage.set_config("twitch_client_id", twitch_client_id.strip())
        storage.set_config("twitch_client_secret", twitch_client_secret.strip())
        storage.set_config("openai_api_key", openai_api_key.strip())
        storage.set_config("tiktok_access_token", tiktok_access_token.strip())
        storage.set_config("laugh_threshold", str(laugh_threshold))
        storage.set_config("clip_duration", str(clip_duration))
        storage.set_config("auto_post", "true" if auto_post else "false")
        storage.set_config("subtitles", "true" if subtitles else "false")
        storage.set_config("default_hashtags", default_hashtags.strip())
        storage.set_config("language", language)
        st.toast("✅ Configuration enregistrée ! Le moteur la prend en compte "
                 "au prochain cycle (~1 minute).")
        st.rerun()

st.divider()
st.caption(f"FQWorld v{VERSION} · agent open-source Twitch → TikTok · "
           "vos clés restent sur votre machine")
