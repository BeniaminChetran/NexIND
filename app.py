#------------------------------
#----app.py (Meniu 2 Niveluri)
#------------------------------

import os
import base64
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
icon_win_path = os.path.join(BASE_DIR, "Nexind.ico")
icon_android_path = os.path.join(BASE_DIR, "Nexind_android.png")

if os.path.exists(icon_android_path):
    page_icon = Image.open(icon_android_path)
elif os.path.exists(icon_win_path):
    page_icon = Image.open(icon_win_path)
else:
    page_icon = "⚙️"

st.set_page_config(
    page_title="NexInd CMMS Enterprise Dashboard",
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

if os.path.exists(icon_android_path):
    st.logo(icon_android_path)

# Inițializare stare globală de deblocare
if "is_unlocked" not in st.session_state:
    st.session_state["is_unlocked"] = False

# Import pagini modulare
from repositories.setari_repository import SetariRepository
from pages.dashboard import render_dashboard
from pages.predictii import render_predictii
from pages.activitati import render_activitati
from pages.mentenanta import render_mentenanta
from pages.istoric import render_istoric
from pages.documentatii import render_documentatii
from pages.masini import render_masini
from pages.piese import render_piese
from pages.firme import render_firme
from pages.masuratori import render_masuratori
from pages.reparatii_electronice import render_reparatii_electronice
from pages.oferte import render_oferte
from pages.setari import render_setari


def seteaza_iconita_android(cale_png: str):
    if os.path.exists(cale_png):
        with open(cale_png, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"
        components.html(
            f"""
            <script>
            (function() {{
                const doc = window.parent.document;
                const head = doc.head;
                doc.querySelectorAll('link[rel*="icon"], link[rel="apple-touch-icon"]').forEach(el => el.remove());
                ['icon', 'shortcut icon', 'apple-touch-icon'].forEach(relType => {{
                    const link = doc.createElement('link');
                    link.rel = relType;
                    link.type = 'image/png';
                    link.href = '{data_uri}';
                    head.appendChild(link);
                }});
            }})();
            </script>
            """,
            height=0,
            width=0,
        )


seteaza_iconita_android(icon_android_path)


def render_deblocare():
    st.subheader("🔐 SistemAdmin — Deblocare Editare Configurații Sisteme")
    st.caption("Controlează accesul pentru adăugarea/ștergerea verificărilor tehnice pe sisteme și a elementelor din componența sistemelor.")

    setari = SetariRepository.get_setari()
    parola_salvata = str(setari.get("pass") or "").strip()

    if not parola_salvata:
        st.warning("⚠️ Nu există nicio parolă configurată în baza de date (`setari.pass`). Setează mai întâi o parolă în **SistemAdmin → Setări**.")

    if st.session_state.get("is_unlocked", False):
        st.success("🔓 **Status curent: DEBLOCAT** — Ai permisiuni complete de adăugare și ștergere la verificările tehnice pe sisteme și la componența sistemelor.")
        if st.button("🔒 Blochează la loc elementele protejate", type="primary"):
            st.session_state["is_unlocked"] = False
            st.toast("🔒 Elementele protejate au fost blocate.")
            st.rerun()
    else:
        st.info("🔒 **Status curent: BLOCAT (Doar vizualizare)** — Introdu parola administratorului din Setări pentru a debloca editarea.")
        with st.form("form_deblocare_admin"):
            parola_introdusa = st.text_input("Parolă administrator", type="password")
            submit_unlock = st.form_submit_button("🔓 Deblochează", type="primary")
            if submit_unlock:
                if not parola_salvata:
                    st.error("Nu este definită o parolă în Setări.")
                elif parola_introdusa == parola_salvata:
                    st.session_state["is_unlocked"] = True
                    st.toast("🔓 Sesiune deblocată cu succes!")
                    st.rerun()
                else:
                    st.error("❌ Parolă incorectă!")


st.sidebar.title("📌 Nexus Control Panel")
st.sidebar.text("CMMS Enterprise v10.5.0")
st.sidebar.markdown("---")
if st.session_state.get("is_unlocked", False):
    st.sidebar.success("🔓 Mod Editare: DEBLOCAT")
else:
    st.sidebar.warning("🔒 Mod Editare: BLOCAT")
st.sidebar.info("Arhitectură Enterprise optimizată.")

st.title("🛠️ NexInd CMMS Dashboard & Predictive")

# Structură bară de meniu (Categorie -> Sub-meniuri)
MENIU_STRUCTURA = {
    "📊 Management & Comercial": {
        "📈 DashBoard": render_dashboard,
        "🔮 Predicții": render_predictii,
        "💼 Oferte de preț": render_oferte,
    },
    "🛠️ Activități": {
        "📝 Intervenții": render_activitati,
        "🛡️ Mentenanță preventivă": render_mentenanta,
        "📊 Măsurători": render_masuratori,
        "⚡ Reparații electronice": render_reparatii_electronice,
    },
    "📦 Nomenclatoare & Stocuri": {
        "📦 Piese": render_piese,
        "⚙️ Mașini": render_masini,
        "🏢 Firme": render_firme,
    },
    "🗂️ Arhivă & Docs": {
        "📋 Istoric": render_istoric,
        "📄 Documentații": render_documentatii,
    },
    "🔐 SistemAdmin": {
        "⚙️ Setări": render_setari,
        "🔑 Deblocare": render_deblocare,
    },
}

col_cat, col_sub = st.columns([1.3, 1.7])
with col_cat:
    categorie_sel = st.selectbox(
        "Meniu Principal",
        options=list(MENIU_STRUCTURA.keys()),
        key="nav_categorie_principala"
    )
with col_sub:
    submeniuri = MENIU_STRUCTURA[categorie_sel]
    submeniu_sel = st.selectbox(
        "Sub-modul",
        options=list(submeniuri.keys()),
        key=f"nav_submeniu_{categorie_sel}"
    )

st.markdown("---")

# Randarea paginii selectate
submeniuri[submeniu_sel]()