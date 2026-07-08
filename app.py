"""
FQWorld — Interface Web ultra-simple de l'agent Twitch → TikTok.

Lancement :  streamlit run app.py
L'utilisateur pilote TOUT depuis ici (streamers, clips, clés API),
le moteur technique (agent/brain.py) tourne en arrière-plan et
communique via la base SQLite partagée (agent/storage.py).
"""

import time
from pathlib import Path

import streamlit as st

from agent import storage
from agent.tiktok_publisher import publish_to_tiktok

st.set_page_config(page_title="FQWorld — Twitch → TikTok", page_icon="🎬", layout="wide")

st.title("🎬 FQWorld — Agent Twitch → TikTok")
st.caption("Détection automatique des moments drôles en live, montage 9:16 et publication TikTok.")

tab_dashboard, tab_library, tab_config = st.tabs(
    ["📡 Dashboard", "🎞️ Bibliothèque de Clips", "⚙️ Configuration"]
)

# ════════════════════════════════════════════════ Onglet 1 : Dashboard
with tab_dashboard:
    st.subheader("Streamers suivis")

    with st.form("add_streamer_form", clear_on_submit=True):
        col_input, col_btn = st.columns([4, 1])
        pseudo = col_input.text_input(
            "Pseudo Twitch", placeholder="ex : squeezie, kameto…",
            label_visibility="collapsed",
        )
        submitted = col_btn.form_submit_button("➕ Ajouter un streamer", use_container_width=True)
        if submitted and pseudo.strip():
            storage.add_streamer(pseudo)
            st.toast(f"✅ {pseudo.strip()} ajouté ! Le cerveau le surveillera d'ici ~1 minute.")

    streamers = storage.list_streamers()
    if not streamers:
        st.info("Aucun streamer suivi pour l'instant. Ajoutez un pseudo ci-dessus 👆")
    else:
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

    st.divider()
    if st.button("🔄 Rafraîchir les statuts"):
        st.rerun()
    st.caption("Les statuts En live / Hors ligne sont mis à jour par le moteur toutes les ~60 s.")

# ════════════════════════════════════ Onglet 2 : Bibliothèque de Clips
with tab_library:
    st.subheader("Clips humoristiques générés")

    clips = storage.list_clips()
    if not clips:
        st.info("Aucun clip pour l'instant. Dès qu'un streamer suivi fera rire son chat, "
                "le clip apparaîtra ici automatiquement. 🍿")
    else:
        badges = {
            storage.CLIP_READY: "🟢 Prêt",
            storage.CLIP_POSTED: "🚀 Posté sur TikTok",
            storage.CLIP_FAILED: "🔴 Échec",
            storage.CLIP_REJECTED: "🟡 Rejeté par l'IA",
        }
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

                    col_pub, col_del = st.columns(2)
                    if clip["status"] != storage.CLIP_POSTED:
                        if col_pub.button("🚀 Publier", key=f"pub_{clip['id']}", use_container_width=True):
                            with st.spinner("Publication sur TikTok…"):
                                ok, message = publish_to_tiktok(clip["path"], clip["title"])
                            if ok:
                                storage.update_clip_status(clip["id"], storage.CLIP_POSTED)
                                st.toast("🚀 Publié sur TikTok !")
                            else:
                                storage.update_clip_status(clip["id"], storage.CLIP_FAILED, error=message)
                                st.toast(f"❌ Échec : {message}")
                            st.rerun()
                    if col_del.button("🗑️ Supprimer", key=f"rm_{clip['id']}", use_container_width=True):
                        storage.delete_clip(clip["id"])
                        st.rerun()

# ═══════════════════════════════════════════ Onglet 3 : Configuration
with tab_config:
    st.subheader("Clés API & réglages")
    st.caption("Tout se configure ici — aucun fichier de code à ouvrir. "
               "Les clés sont stockées localement dans `data/agent.db`.")

    current = storage.get_all_config()
    with st.form("config_form"):
        new_values = {}
        st.markdown("##### 🔑 Clés API")
        for key, meta in storage.CONFIG_KEYS.items():
            if key in ("laugh_threshold", "clip_duration", "auto_post"):
                continue
            new_values[key] = st.text_input(
                meta["label"],
                value=current.get(key, ""),
                type="password" if meta["secret"] else "default",
            )

        st.markdown("##### 🎛️ Réglages de détection")
        new_values["laugh_threshold"] = str(st.slider(
            "Sensibilité : pic de rires requis (× l'activité normale du chat)",
            min_value=2, max_value=10, value=int(float(current.get("laugh_threshold", "4"))),
        ))
        new_values["clip_duration"] = str(st.slider(
            "Durée des clips (secondes)",
            min_value=15, max_value=60, value=int(float(current.get("clip_duration", "30"))),
        ))
        auto = st.toggle(
            "Publier automatiquement sur TikTok (sinon les clips attendent en « Prêt »)",
            value=current.get("auto_post", "false") == "true",
        )
        new_values["auto_post"] = "true" if auto else "false"

        if st.form_submit_button("💾 Enregistrer la configuration"):
            for key, value in new_values.items():
                storage.set_config(key, value)
            st.success("Configuration enregistrée ! Le moteur la prendra en compte au prochain cycle.")

    st.divider()
    st.markdown(
        "**Où trouver les clés ?**\n"
        "- Twitch : https://dev.twitch.tv/console/apps (créer une application → Client ID + Secret)\n"
        "- OpenAI : https://platform.openai.com/api-keys\n"
        "- TikTok : https://developers.tiktok.com (Content Posting API)"
    )
